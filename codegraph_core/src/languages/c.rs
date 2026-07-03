use tree_sitter::{Node as TSNode, Parser};

use crate::parser::{
    make_calls_edge, make_contains_edge, make_external_node, make_file_node, make_imports_edge,
    make_references_edge, node_text, stable_id, ParsedEdge, ParsedNode,
};

pub fn parse(path: &str) -> (Vec<ParsedNode>, Vec<ParsedEdge>) {
    let source = match std::fs::read(path) {
        Ok(s) => s,
        Err(_) => return (vec![], vec![]),
    };
    let mut parser = Parser::new();
    parser
        .set_language(&tree_sitter_c::LANGUAGE.into())
        .unwrap();
    let tree = match parser.parse(&source, None) {
        Some(t) => t,
        None => return (vec![], vec![]),
    };

    let file_node = make_file_node(path, "c");
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
    );
    (nodes, edges)
}

fn walk(
    node: TSNode,
    parent_id: &str,
    file_path: &str,
    nodes: &mut Vec<ParsedNode>,
    edges: &mut Vec<ParsedEdge>,
    source: &[u8],
) {
    let current_id: String;

    match node.kind() {
        "function_definition" => {
            if let Some(name) = function_name(&node, source) {
                let id = stable_id(&format!("function:c:{}", name));
                let line = node.start_position().row as u32 + 1;
                let col = node.start_position().column as u32;
                nodes.push(ParsedNode {
                    id: id.clone(),
                    kind: "function".to_string(),
                    name: name.clone(),
                    qualified_name: Some(name),
                    file_path: Some(file_path.to_string()),
                    line_start: Some(line),
                    line_end: Some(node.end_position().row as u32 + 1),
                    language: "c".to_string(),
                    metadata: serde_json::json!({}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                current_id = id;
                for i in 0..node.named_child_count() {
                    walk(node.named_child(i).unwrap(), &current_id, file_path, nodes, edges, source);
                }
                return;
            }
        }

        "struct_specifier" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(&name_node, source);
                let id = stable_id(&format!("type:c:{}", name));
                let line = node.start_position().row as u32 + 1;
                let col = node.start_position().column as u32;
                nodes.push(ParsedNode {
                    id: id.clone(),
                    kind: "type".to_string(),
                    name: name.clone(),
                    qualified_name: Some(name),
                    file_path: Some(file_path.to_string()),
                    line_start: Some(line),
                    line_end: Some(node.end_position().row as u32 + 1),
                    language: "c".to_string(),
                    metadata: serde_json::json!({"struct": true}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
            }
            return; // don't recurse into struct body
        }

        "preproc_include" => {
            handle_include(&node, parent_id, file_path, nodes, edges, source);
            return;
        }

        "call_expression" => {
            handle_call(&node, parent_id, file_path, edges, source);
            // recurse into children for nested calls is skipped (matches Python behaviour)
            return;
        }

        "type_identifier" => {
            let type_name = node_text(&node, source);
            let type_id = stable_id(&format!("type:c:{}", type_name));
            let line = node.start_position().row as u32 + 1;
            let col = node.start_position().column as u32;
            nodes.push(make_external_node(&type_name, "c", "type"));
            edges.push(make_references_edge(parent_id, &type_id, file_path, line, col));
            return;
        }

        _ => {}
    }

    for i in 0..node.named_child_count() {
        walk(node.named_child(i).unwrap(), parent_id, file_path, nodes, edges, source);
    }
}

pub fn function_name(node: &TSNode, source: &[u8]) -> Option<String> {
    let decl = node.child_by_field_name("declarator")?;
    declarator_name(&decl, source)
}

pub fn declarator_name(node: &TSNode, source: &[u8]) -> Option<String> {
    match node.kind() {
        "identifier" | "field_identifier" => Some(node_text(node, source)),
        "function_declarator" => {
            let inner = node.child_by_field_name("declarator")?;
            declarator_name(&inner, source)
        }
        "pointer_declarator" => {
            let inner = node.child_by_field_name("declarator")?;
            declarator_name(&inner, source)
        }
        _ => {
            for i in 0..node.named_child_count() {
                if let Some(name) = declarator_name(&node.named_child(i).unwrap(), source) {
                    return Some(name);
                }
            }
            None
        }
    }
}

pub fn handle_include(
    node: &TSNode,
    parent_id: &str,
    file_path: &str,
    nodes: &mut Vec<ParsedNode>,
    edges: &mut Vec<ParsedEdge>,
    source: &[u8],
) {
    let path_node = node
        .child_by_field_name("path")
        .or_else(|| node.named_child(0));
    if let Some(path_node) = path_node {
        let raw = node_text(&path_node, source)
            .trim_matches(|c| c == '<' || c == '>' || c == '"')
            .to_string();
        let ext = make_external_node(&raw, "c", "module");
        let line = node.start_position().row as u32 + 1;
        let col = node.start_position().column as u32;
        edges.push(make_imports_edge(parent_id, &ext.id, file_path, line, col));
        nodes.push(ext);
    }
}

pub fn handle_call(
    node: &TSNode,
    caller_id: &str,
    file_path: &str,
    edges: &mut Vec<ParsedEdge>,
    source: &[u8],
) {
    if let Some(fn_node) = node.child_by_field_name("function") {
        let name = node_text(&fn_node, source);
        let callee_id = stable_id(&format!("function:c:{}", name));
        let line = node.start_position().row as u32 + 1;
        let col = node.start_position().column as u32;
        edges.push(make_calls_edge(caller_id, &callee_id, file_path, line, col));
    }
}
