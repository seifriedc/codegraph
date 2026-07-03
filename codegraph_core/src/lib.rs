use pyo3::prelude::*;

mod graph;
mod languages;
mod parser;

pub use parser::{ParsedEdge, ParsedNode};

#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Parse a source file and return (nodes_json, edges_json).
#[pyfunction]
fn parse_file(path: &str, language: &str) -> PyResult<(String, String)> {
    let (nodes, edges) = languages::parse(path, language);
    let nodes_json = serde_json::to_string(&nodes)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    let edges_json = serde_json::to_string(&edges)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    Ok((nodes_json, edges_json))
}

/// Return the raw AST of a source file as a JSON string.
#[pyfunction]
fn get_ast(_path: &str, _language: &str) -> PyResult<String> {
    // Placeholder — will call tree-sitter and serialize the AST.
    Ok("{}".to_string())
}

/// BFS traversal over an edge list provided as JSON.
/// edges_json: [{"source_id": "...", "target_id": "...", "kind": "..."}, ...]
/// Returns a JSON array of reachable node IDs (excluding start_id).
#[pyfunction]
fn traverse(
    start_id: &str,
    edges_json: &str,
    edge_kinds: Vec<String>,
    direction: &str,
    max_depth: usize,
) -> PyResult<String> {
    let edges: Vec<graph::EdgeData> = serde_json::from_str(edges_json)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    let ids = graph::bfs(&start_id, &edges, &edge_kinds, direction, max_depth);
    serde_json::to_string(&ids)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
}

#[pymodule]
fn codegraph_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(parse_file, m)?)?;
    m.add_function(wrap_pyfunction!(get_ast, m)?)?;
    m.add_function(wrap_pyfunction!(traverse, m)?)?;
    Ok(())
}
