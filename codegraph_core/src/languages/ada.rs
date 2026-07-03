use tree_sitter::{Node as TSNode, Parser};

use crate::parser::{
    make_calls_edge, make_contains_edge, make_external_node, make_file_node, make_imports_edge,
    make_inherits_edge, make_instantiates_edge, make_references_edge, node_text, stable_id,
    ParsedEdge, ParsedNode,
};

const TRANSPARENT: &[&str] = &[
    "compilation",
    "compilation_unit",
    "non_empty_declarative_part",
    "declarative_part",
    "handled_sequence_of_statements",
    "sequence_of_statements",
    "record_definition",
    "record_extension_part",
    "component_list",
];

pub fn parse(path: &str) -> (Vec<ParsedNode>, Vec<ParsedEdge>) {
    let source = match std::fs::read(path) {
        Ok(s) => s,
        Err(_) => return (vec![], vec![]),
    };
    let mut parser = Parser::new();
    parser
        .set_language(&tree_sitter_ada::LANGUAGE.into())
        .unwrap();
    let tree = match parser.parse(&source, None) {
        Some(t) => t,
        None => return (vec![], vec![]),
    };

    let file_node = make_file_node(path, "ada");
    let file_id = file_node.id.clone();
    let mut nodes = vec![file_node];
    let mut edges = vec![];

    walk(
        tree.root_node(),
        &file_id,
        path,
        &mut nodes,
        &mut edges,
        &source,
        None,
    );
    (nodes, edges)
}

/// Recursively build a dotted name from a selected_component or identifier node.
fn selected_name(node: &TSNode, source: &[u8]) -> String {
    match node.kind() {
        "identifier" => node_text(node, source),
        "selected_component" if node.named_child_count() >= 2 => {
            let left = selected_name(&node.named_child(0).unwrap(), source);
            let right = selected_name(&node.named_child(1).unwrap(), source);
            format!("{}.{}", left, right)
        }
        _ => node_text(node, source),
    }
}

/// Return (Some(dotted_name), is_already_qualified) for the first identifier or
/// selected_component child. is_already_qualified means don't prefix with parent_qname.
fn first_name(node: &TSNode, source: &[u8]) -> (Option<String>, bool) {
    for i in 0..node.named_child_count() {
        let child = node.named_child(i).unwrap();
        match child.kind() {
            "identifier" => return (Some(node_text(&child, source)), false),
            "selected_component" => return (Some(selected_name(&child, source)), true),
            _ => {}
        }
    }
    (None, false)
}

fn subprogram_spec<'tree>(node: &TSNode<'tree>) -> Option<TSNode<'tree>> {
    for i in 0..node.named_child_count() {
        let child = node.named_child(i).unwrap();
        if matches!(child.kind(), "function_specification" | "procedure_specification") {
            return Some(child);
        }
    }
    None
}

fn resolve_type_name(raw: &str, parent_qname: Option<&str>) -> String {
    if !raw.contains('.') {
        if let Some(pq) = parent_qname {
            if let Some(dot) = pq.rfind('.') {
                return format!("{}.{}", &pq[..dot], raw);
            }
        }
    }
    raw.to_string()
}

fn emit_type_ref(
    name_node: &TSNode,
    parent_id: &str,
    parent_qname: Option<&str>,
    file_path: &str,
    nodes: &mut Vec<ParsedNode>,
    edges: &mut Vec<ParsedEdge>,
    source: &[u8],
) {
    let raw = selected_name(name_node, source);
    let type_name = resolve_type_name(&raw, parent_qname);
    let type_id = stable_id(&format!("type:ada:{}", type_name));
    let line = name_node.start_position().row as u32 + 1;
    let col = name_node.start_position().column as u32;
    nodes.push(make_external_node(&type_name, "ada", "type"));
    edges.push(make_references_edge(parent_id, &type_id, file_path, line, col));
}

fn walk(
    node: TSNode,
    parent_id: &str,
    file_path: &str,
    nodes: &mut Vec<ParsedNode>,
    edges: &mut Vec<ParsedEdge>,
    source: &[u8],
    parent_qname: Option<&str>,
) {
    if TRANSPARENT.contains(&node.kind()) {
        for i in 0..node.named_child_count() {
            walk(node.named_child(i).unwrap(), parent_id, file_path, nodes, edges, source, parent_qname);
        }
        return;
    }

    let mut current_id = parent_id.to_string();
    let mut current_qname: Option<String> = parent_qname.map(|s| s.to_string());

    match node.kind() {
        "package_declaration" | "package_body" => {
            let (full_name, _) = first_name(&node, source);
            if let Some(full_name) = full_name {
                let qname = full_name.clone();
                let name = full_name.rsplit('.').next().unwrap_or(&full_name).to_string();
                let id = stable_id(&format!("package:ada:{}", qname));
                let line = node.start_position().row as u32 + 1;
                let col = node.start_position().column as u32;
                nodes.push(ParsedNode {
                    id: id.clone(),
                    kind: "package".to_string(),
                    name,
                    qualified_name: Some(qname.clone()),
                    file_path: Some(file_path.to_string()),
                    line_start: Some(line),
                    line_end: Some(node.end_position().row as u32 + 1),
                    language: "ada".to_string(),
                    metadata: serde_json::json!({}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                current_id = id;
                current_qname = Some(qname);
            }
        }

        "subprogram_declaration" | "subprogram_body" => {
            if let Some(spec) = subprogram_spec(&node) {
                let (raw_name, is_qualified) = first_name(&spec, source);
                if let Some(raw_name) = raw_name {
                    let qname = if is_qualified {
                        raw_name.clone()
                    } else {
                        match &current_qname {
                            Some(pq) => format!("{}.{}", pq, raw_name),
                            None => raw_name.clone(),
                        }
                    };
                    let name = raw_name.rsplit('.').next().unwrap_or(&raw_name).to_string();
                    let subkind = spec.kind().split('_').next().unwrap_or("function");
                    let id = stable_id(&format!("function:ada:{}", qname));
                    let line = node.start_position().row as u32 + 1;
                    let col = node.start_position().column as u32;
                    nodes.push(ParsedNode {
                        id: id.clone(),
                        kind: "function".to_string(),
                        name,
                        qualified_name: Some(qname.clone()),
                        file_path: Some(file_path.to_string()),
                        line_start: Some(line),
                        line_end: Some(node.end_position().row as u32 + 1),
                        language: "ada".to_string(),
                        metadata: serde_json::json!({ "subkind": subkind }),
                    });
                    edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                    current_id = id;
                    current_qname = Some(qname);
                }
            }
        }

        "full_type_declaration" => {
            let (name, _) = first_name(&node, source);
            if let Some(name) = name {
                let qname = match &current_qname {
                    Some(pq) => format!("{}.{}", pq, name),
                    None => name.clone(),
                };
                let id = stable_id(&format!("type:ada:{}", qname));
                let line = node.start_position().row as u32 + 1;
                let col = node.start_position().column as u32;
                nodes.push(ParsedNode {
                    id: id.clone(),
                    kind: "type".to_string(),
                    name,
                    qualified_name: Some(qname.clone()),
                    file_path: Some(file_path.to_string()),
                    line_start: Some(line),
                    line_end: Some(node.end_position().row as u32 + 1),
                    language: "ada".to_string(),
                    metadata: serde_json::json!({}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));

                // Check for derived type → inherits edge
                for i in 0..node.named_child_count() {
                    let child = node.named_child(i).unwrap();
                    if child.kind() == "derived_type_definition" {
                        let (parent_name, _) = first_name(&child, source);
                        if let Some(parent_name) = parent_name {
                            let parent_id = stable_id(&format!("type:ada:{}", parent_name));
                            edges.push(make_inherits_edge(&id, &parent_id, file_path, line, col));
                        }
                        break;
                    }
                }

                current_id = id;
                current_qname = Some(qname);
            }
        }

        "component_declaration" => {
            // Collect all names before component_definition (e.g. "X, Y : Float" has two)
            let mut field_names: Vec<String> = Vec::new();
            for i in 0..node.named_child_count() {
                let child = node.named_child(i).unwrap();
                if child.kind() == "component_definition" {
                    break;
                }
                if child.kind() == "identifier" {
                    field_names.push(node_text(&child, source));
                }
            }
            if !field_names.is_empty() {
                if let Some(pq) = &current_qname {
                    let line = node.start_position().row as u32 + 1;
                    let col = node.start_position().column as u32;
                    for field_name in &field_names {
                        let qname = format!("{}.{}", pq, field_name);
                        let id = stable_id(&format!("field:ada:{}", qname));
                        nodes.push(ParsedNode {
                            id: id.clone(),
                            kind: "field".to_string(),
                            name: field_name.clone(),
                            qualified_name: Some(qname),
                            file_path: Some(file_path.to_string()),
                            line_start: Some(line),
                            line_end: Some(node.end_position().row as u32 + 1),
                            language: "ada".to_string(),
                            metadata: serde_json::json!({}),
                        });
                        edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                    }
                }
            }
            // Fall through so component_definition is visited for the field type reference
        }

        // Type reference contexts — Ada grammar uses plain identifiers rather than a
        // separate subtype_mark node, so we handle each structural context explicitly.

        "component_definition" => {
            // The first identifier/selected_component child is the field's type
            if let Some(child) = node.named_child(0) {
                if matches!(child.kind(), "identifier" | "selected_component") {
                    emit_type_ref(&child, parent_id, parent_qname, file_path, nodes, edges, source);
                }
            }
            return;
        }

        "parameter_specification" => {
            // Last identifier/selected_component child is the type; preceding ones are param names
            let mut type_node = None;
            for i in 0..node.named_child_count() {
                let child = node.named_child(i).unwrap();
                if matches!(child.kind(), "identifier" | "selected_component") {
                    type_node = Some(child);
                }
            }
            if let Some(tn) = type_node {
                emit_type_ref(&tn, parent_id, parent_qname, file_path, nodes, edges, source);
            }
            return;
        }

        "result_profile" => {
            // Single child is the return type
            if let Some(child) = node.named_child(0) {
                if matches!(child.kind(), "identifier" | "selected_component") {
                    emit_type_ref(&child, parent_id, parent_qname, file_path, nodes, edges, source);
                }
            }
            return;
        }

        "with_clause" => {
            for i in 0..node.named_child_count() {
                let child = node.named_child(i).unwrap();
                if matches!(child.kind(), "identifier" | "selected_component") {
                    let pkg_name = selected_name(&child, source);
                    let ext = make_external_node(&pkg_name, "ada", "package");
                    let line = node.start_position().row as u32 + 1;
                    let col = node.start_position().column as u32;
                    edges.push(make_imports_edge(parent_id, &ext.id, file_path, line, col));
                    nodes.push(ext);
                }
            }
            return;
        }

        "procedure_call_statement" | "function_call" => {
            // Skip Ada attribute calls (e.g. Positive'Max) — they have a tick child
            let is_attribute_call = (0..node.named_child_count())
                .any(|i| node.named_child(i).unwrap().kind() == "tick");
            if !is_attribute_call {
                if let Some(name_child) = node.named_child(0) {
                    let raw_name = selected_name(&name_child, source);
                    // Resolve unqualified names against the enclosing package scope
                    let callee_name = if !raw_name.contains('.') {
                        match parent_qname {
                            Some(pq) => match pq.rfind('.') {
                                Some(dot) => format!("{}.{}", &pq[..dot], raw_name),
                                None => raw_name,
                            },
                            None => raw_name,
                        }
                    } else {
                        raw_name
                    };
                    let callee_id = stable_id(&format!("function:ada:{}", callee_name));
                    let line = node.start_position().row as u32 + 1;
                    let col = node.start_position().column as u32;
                    // Placeholder node so the callee is queryable even if not indexed
                    nodes.push(make_external_node(&callee_name, "ada", "function"));
                    edges.push(make_calls_edge(parent_id, &callee_id, file_path, line, col));
                }
            }
            // Fall through to recurse into arguments — catches nested function calls
        }

        "generic_instantiation" => {
            let (raw_name, is_qualified) = first_name(&node, source);
            if let Some(raw_name) = raw_name {
                let qname = if is_qualified {
                    raw_name.clone()
                } else {
                    match &current_qname {
                        Some(pq) => format!("{}.{}", pq, raw_name),
                        None => raw_name.clone(),
                    }
                };
                let name = raw_name.rsplit('.').next().unwrap_or(&raw_name).to_string();
                let id = stable_id(&format!("package:ada:{}", qname));
                let line = node.start_position().row as u32 + 1;
                let col = node.start_position().column as u32;
                nodes.push(ParsedNode {
                    id: id.clone(),
                    kind: "package".to_string(),
                    name,
                    qualified_name: Some(qname),
                    file_path: Some(file_path.to_string()),
                    line_start: Some(line),
                    line_end: Some(node.end_position().row as u32 + 1),
                    language: "ada".to_string(),
                    metadata: serde_json::json!({}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                // The generic being instantiated is the second identifier/selected_component
                let mut found_first = false;
                for i in 0..node.named_child_count() {
                    let child = node.named_child(i).unwrap();
                    if matches!(child.kind(), "identifier" | "selected_component") {
                        if found_first {
                            let generic_name = selected_name(&child, source);
                            let generic_id = stable_id(&format!("package:ada:{}", generic_name));
                            edges.push(make_instantiates_edge(&id, &generic_id, file_path, line, col));
                            break;
                        }
                        found_first = true;
                    }
                }
            }
            // Fall through to recurse
        }

        _ => {}
    }

    for i in 0..node.named_child_count() {
        walk(
            node.named_child(i).unwrap(),
            &current_id,
            file_path,
            nodes,
            edges,
            source,
            current_qname.as_deref(),
        );
    }
}
