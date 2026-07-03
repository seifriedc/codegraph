use serde::{Deserialize, Serialize};

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
