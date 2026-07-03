use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Namespace UUID matching Python's stable_id: uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
const UUID_NS: Uuid = Uuid::from_bytes([
    0x6b, 0xa7, 0xb8, 0x10, 0x9d, 0xad, 0x11, 0xd1,
    0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8,
]);

pub fn stable_id(name: &str) -> String {
    Uuid::new_v5(&UUID_NS, name.as_bytes()).to_string()
}

pub fn random_id() -> String {
    Uuid::new_v4().to_string()
}

pub fn node_text(node: &tree_sitter::Node, source: &[u8]) -> String {
    node.utf8_text(source).unwrap_or("").to_string()
}

pub fn make_contains_edge(
    source_id: &str, target_id: &str, file_path: &str,
    line: u32, col: u32,
) -> ParsedEdge {
    ParsedEdge {
        id: random_id(),
        kind: "contains".to_string(),
        source_id: source_id.to_string(),
        target_id: target_id.to_string(),
        file_path: Some(file_path.to_string()),
        line: Some(line),
        col: Some(col),
    }
}

pub fn make_imports_edge(
    source_id: &str, target_id: &str, file_path: &str,
    line: u32, col: u32,
) -> ParsedEdge {
    ParsedEdge {
        id: random_id(),
        kind: "imports".to_string(),
        source_id: source_id.to_string(),
        target_id: target_id.to_string(),
        file_path: Some(file_path.to_string()),
        line: Some(line),
        col: Some(col),
    }
}

pub fn make_calls_edge(
    source_id: &str, target_id: &str, file_path: &str,
    line: u32, col: u32,
) -> ParsedEdge {
    ParsedEdge {
        id: random_id(),
        kind: "calls".to_string(),
        source_id: source_id.to_string(),
        target_id: target_id.to_string(),
        file_path: Some(file_path.to_string()),
        line: Some(line),
        col: Some(col),
    }
}

pub fn make_inherits_edge(
    source_id: &str, target_id: &str, file_path: &str,
    line: u32, col: u32,
) -> ParsedEdge {
    ParsedEdge {
        id: random_id(),
        kind: "inherits".to_string(),
        source_id: source_id.to_string(),
        target_id: target_id.to_string(),
        file_path: Some(file_path.to_string()),
        line: Some(line),
        col: Some(col),
    }
}

pub fn make_references_edge(
    source_id: &str, target_id: &str, file_path: &str,
    line: u32, col: u32,
) -> ParsedEdge {
    ParsedEdge {
        id: random_id(),
        kind: "references".to_string(),
        source_id: source_id.to_string(),
        target_id: target_id.to_string(),
        file_path: Some(file_path.to_string()),
        line: Some(line),
        col: Some(col),
    }
}

pub fn make_instantiates_edge(
    source_id: &str, target_id: &str, file_path: &str,
    line: u32, col: u32,
) -> ParsedEdge {
    ParsedEdge {
        id: random_id(),
        kind: "instantiates".to_string(),
        source_id: source_id.to_string(),
        target_id: target_id.to_string(),
        file_path: Some(file_path.to_string()),
        line: Some(line),
        col: Some(col),
    }
}

pub fn make_file_node(path: &str, language: &str) -> ParsedNode {
    let name = std::path::Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(path)
        .to_string();
    ParsedNode {
        id: stable_id(&format!("file:{}", path)),
        kind: "file".to_string(),
        name,
        qualified_name: Some(path.to_string()),
        file_path: Some(path.to_string()),
        line_start: Some(1),
        line_end: None,
        language: language.to_string(),
        metadata: serde_json::json!({}),
    }
}

pub fn make_external_node(qualified_name: &str, language: &str, kind: &str) -> ParsedNode {
    let name = qualified_name
        .rsplit('.')
        .next()
        .unwrap_or(qualified_name)
        .to_string();
    ParsedNode {
        id: stable_id(&format!("{}:{}:{}", kind, language, qualified_name)),
        kind: kind.to_string(),
        name,
        qualified_name: Some(qualified_name.to_string()),
        file_path: None,
        line_start: None,
        line_end: None,
        language: language.to_string(),
        metadata: serde_json::json!({}),
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ParsedNode {
    pub id: String,
    pub kind: String,
    pub name: String,
    pub qualified_name: Option<String>,
    pub file_path: Option<String>,
    pub line_start: Option<u32>,
    pub line_end: Option<u32>,
    pub language: String,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ParsedEdge {
    pub id: String,
    pub kind: String,
    pub source_id: String,
    pub target_id: String,
    pub file_path: Option<String>,
    pub line: Option<u32>,
    pub col: Option<u32>,
}
