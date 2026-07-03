use pyo3::prelude::*;

mod graph;
mod parser;

pub use parser::{ParsedEdge, ParsedNode};

#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Parse a source file and return (nodes, edges) as JSON strings.
/// This is the fast path once the Python-only parsers are migrated.
#[pyfunction]
fn parse_file(_path: &str, _language: &str) -> PyResult<(String, String)> {
    // Placeholder — Python parsers handle this until migration is complete.
    Ok(("[]".to_string(), "[]".to_string()))
}

/// Return the raw AST of a source file as a JSON string.
#[pyfunction]
fn get_ast(_path: &str, _language: &str) -> PyResult<String> {
    // Placeholder — will call tree-sitter and serialize the AST.
    Ok("{}".to_string())
}

/// BFS/DFS graph traversal over nodes/edges provided as JSON.
#[pyfunction]
fn traverse(
    _start_id: &str,
    _nodes_json: &str,
    _edges_json: &str,
    _edge_kinds: Vec<String>,
    _direction: &str,
    _max_depth: usize,
) -> PyResult<String> {
    // Placeholder — will implement fast graph traversal.
    Ok("[]".to_string())
}

#[pymodule]
fn codegraph_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(parse_file, m)?)?;
    m.add_function(wrap_pyfunction!(get_ast, m)?)?;
    m.add_function(wrap_pyfunction!(traverse, m)?)?;
    Ok(())
}
