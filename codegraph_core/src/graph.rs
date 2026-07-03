use std::collections::{HashMap, HashSet, VecDeque};

use serde::Deserialize;

#[derive(Deserialize)]
pub struct EdgeData {
    pub source_id: String,
    pub target_id: String,
    pub kind: String,
}

/// BFS from `start_id` over the provided edge list.
/// Returns IDs of all reachable nodes (excluding start_id itself), up to `max_depth` hops.
pub fn bfs(
    start_id: &str,
    edges: &[EdgeData],
    edge_kinds: &[String],
    direction: &str,
    max_depth: usize,
) -> Vec<String> {
    // Build adjacency map: node_id → [(neighbor_id, edge_kind)]
    let mut adj: HashMap<&str, Vec<(&str, &str)>> = HashMap::new();
    for edge in edges {
        let (from, to) = if direction == "out" {
            (edge.source_id.as_str(), edge.target_id.as_str())
        } else {
            (edge.target_id.as_str(), edge.source_id.as_str())
        };
        adj.entry(from).or_default().push((to, edge.kind.as_str()));
    }

    let mut visited: HashSet<&str> = HashSet::new();
    let mut queue: VecDeque<(&str, usize)> = VecDeque::new();
    visited.insert(start_id);
    queue.push_back((start_id, 0));

    let mut reachable: Vec<String> = Vec::new();

    while let Some((node_id, depth)) = queue.pop_front() {
        if depth >= max_depth {
            continue;
        }
        if let Some(neighbors) = adj.get(node_id) {
            for &(neighbor, kind) in neighbors {
                if !edge_kinds.is_empty() && !edge_kinds.iter().any(|k| k == kind) {
                    continue;
                }
                if visited.insert(neighbor) {
                    reachable.push(neighbor.to_string());
                    queue.push_back((neighbor, depth + 1));
                }
            }
        }
    }

    reachable
}
