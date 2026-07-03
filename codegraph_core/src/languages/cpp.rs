use tree_sitter::{Node as TSNode, Parser};

use crate::parser::{
    make_contains_edge, make_external_node, make_inherits_edge, make_references_edge,
    make_file_node, node_text, stable_id, ParsedEdge, ParsedNode,
};
use super::c::{declarator_name, function_name, handle_call, handle_include};

pub fn parse(path: &str) -> (Vec<ParsedNode>, Vec<ParsedEdge>) {
    let source = match std::fs::read(path) {
        Ok(s) => s,
        Err(_) => return (vec![], vec![]),
    };
    let mut parser = Parser::new();
    parser
        .set_language(&tree_sitter_cpp::LANGUAGE.into())
        .unwrap();
    let tree = match parser.parse(&source, None) {
        Some(t) => t,
        None => return (vec![], vec![]),
    };

    let file_node = make_file_node(path, "cpp");
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

fn walk(
    node: TSNode,
    parent_id: &str,
    file_path: &str,
    nodes: &mut Vec<ParsedNode>,
    edges: &mut Vec<ParsedEdge>,
    source: &[u8],
    class_context: Option<(&str, &str)>, // (class_id, class_qname)
) {
    match node.kind() {
        "class_specifier" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(&name_node, source);
                let qname = match class_context {
                    Some((_, ctx_qname)) => format!("{}::{}", ctx_qname, name),
                    None => name.clone(),
                };
                let id = stable_id(&format!("class:cpp:{}", qname));
                let line = node.start_position().row as u32 + 1;
                let col = node.start_position().column as u32;
                nodes.push(ParsedNode {
                    id: id.clone(),
                    kind: "class".to_string(),
                    name,
                    qualified_name: Some(qname.clone()),
                    file_path: Some(file_path.to_string()),
                    line_start: Some(line),
                    line_end: Some(node.end_position().row as u32 + 1),
                    language: "cpp".to_string(),
                    metadata: serde_json::json!({}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                handle_base_classes(&node, &id, file_path, edges, source);
                if let Some(body) = node.child_by_field_name("body") {
                    for i in 0..body.named_child_count() {
                        walk(
                            body.named_child(i).unwrap(),
                            &id,
                            file_path,
                            nodes,
                            edges,
                            source,
                            Some((&id, &qname)),
                        );
                    }
                }
            }
            return;
        }

        "struct_specifier" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(&name_node, source);
                let id = stable_id(&format!("type:cpp:{}", name));
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
                    language: "cpp".to_string(),
                    metadata: serde_json::json!({"struct": true}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
            }
            return;
        }

        "function_definition" => {
            if let Some(name) = function_name(&node, source) {
                let qname = match class_context {
                    Some((_, ctx_qname)) => format!("{}::{}", ctx_qname, name),
                    None => name.clone(),
                };
                let kind = if class_context.is_some() { "method" } else { "function" };
                let id = stable_id(&format!("function:cpp:{}", qname));
                let line = node.start_position().row as u32 + 1;
                let col = node.start_position().column as u32;
                nodes.push(ParsedNode {
                    id: id.clone(),
                    kind: kind.to_string(),
                    name,
                    qualified_name: Some(qname),
                    file_path: Some(file_path.to_string()),
                    line_start: Some(line),
                    line_end: Some(node.end_position().row as u32 + 1),
                    language: "cpp".to_string(),
                    metadata: serde_json::json!({}),
                });
                edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                // Recurse with new parent for nested calls
                for i in 0..node.named_child_count() {
                    walk(node.named_child(i).unwrap(), &id, file_path, nodes, edges, source, class_context);
                }
                return;
            }
        }

        "field_declaration" => {
            if let Some(class_ctx) = class_context {
                if let Some(fn_decl) = find_function_declarator(&node) {
                    if let Some(name) = declarator_name(&fn_decl, source) {
                        let qname = format!("{}::{}", class_ctx.1, name);
                        let id = stable_id(&format!("function:cpp:{}", qname));
                        let line = node.start_position().row as u32 + 1;
                        let col = node.start_position().column as u32;
                        nodes.push(ParsedNode {
                            id: id.clone(),
                            kind: "method".to_string(),
                            name,
                            qualified_name: Some(qname),
                            file_path: Some(file_path.to_string()),
                            line_start: Some(line),
                            line_end: Some(node.end_position().row as u32 + 1),
                            language: "cpp".to_string(),
                            metadata: serde_json::json!({"declaration_only": true}),
                        });
                        edges.push(make_contains_edge(parent_id, &id, file_path, line, col));
                    }
                }
            }
            return;
        }

        "template_declaration" => {
            for i in 0..node.named_child_count() {
                walk(node.named_child(i).unwrap(), parent_id, file_path, nodes, edges, source, class_context);
            }
            return;
        }

        "preproc_include" => {
            handle_include(&node, parent_id, file_path, nodes, edges, source);
            return;
        }

        "call_expression" => {
            handle_call(&node, parent_id, file_path, edges, source);
            return;
        }

        "type_identifier" => {
            let type_name = node_text(&node, source);
            let type_id = stable_id(&format!("type:cpp:{}", type_name));
            let line = node.start_position().row as u32 + 1;
            let col = node.start_position().column as u32;
            nodes.push(make_external_node(&type_name, "cpp", "type"));
            edges.push(make_references_edge(parent_id, &type_id, file_path, line, col));
            return;
        }

        "qualified_identifier" => {
            // e.g. std::string, std::vector<int> — type reference in a declaration context
            let type_name = node_text(&node, source);
            let type_id = stable_id(&format!("type:cpp:{}", type_name));
            let line = node.start_position().row as u32 + 1;
            let col = node.start_position().column as u32;
            nodes.push(make_external_node(&type_name, "cpp", "type"));
            edges.push(make_references_edge(parent_id, &type_id, file_path, line, col));
            return;
        }

        _ => {}
    }

    for i in 0..node.named_child_count() {
        walk(node.named_child(i).unwrap(), parent_id, file_path, nodes, edges, source, class_context);
    }
}

fn find_function_declarator<'tree>(node: &TSNode<'tree>) -> Option<TSNode<'tree>> {
    for i in 0..node.named_child_count() {
        let child = node.named_child(i).unwrap();
        match child.kind() {
            "function_declarator" => return Some(child),
            "pointer_declarator" => {
                if let Some(inner) = find_function_declarator(&child) {
                    return Some(inner);
                }
            }
            _ => {}
        }
    }
    None
}

fn handle_base_classes(
    class_node: &TSNode,
    child_id: &str,
    file_path: &str,
    edges: &mut Vec<ParsedEdge>,
    source: &[u8],
) {
    for i in 0..class_node.named_child_count() {
        let child = class_node.named_child(i).unwrap();
        if child.kind() != "base_class_clause" {
            continue;
        }
        for j in 0..child.named_child_count() {
            let base = child.named_child(j).unwrap();
            if matches!(base.kind(), "type_identifier" | "qualified_identifier" | "identifier") {
                let parent_name = node_text(&base, source);
                let parent_id = stable_id(&format!("class:cpp:{}", parent_name));
                let line = child.start_position().row as u32 + 1;
                let col = child.start_position().column as u32;
                edges.push(make_inherits_edge(child_id, &parent_id, file_path, line, col));
            }
        }
        break;
    }
}
