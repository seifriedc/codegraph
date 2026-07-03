pub mod ada;
pub mod c;
pub mod cpp;

use crate::parser::{make_file_node, ParsedEdge, ParsedNode};

pub fn parse(path: &str, language: &str) -> (Vec<ParsedNode>, Vec<ParsedEdge>) {
    match language {
        "ada" => ada::parse(path),
        "c" => c::parse(path),
        "cpp" => cpp::parse(path),
        _ => (vec![make_file_node(path, language)], vec![]),
    }
}
