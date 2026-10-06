// Layered top-to-bottom layout for hierarchy views (ADR 0003: dagre, vendored). Pure: `dagre`
// is injected, no DOM, no Cytoscape.

export const HIERARCHY_MODES = ["type", "declaration"];

/**
 * Positions for a hierarchy response as {id: {x, y}} (node centres).
 * nodes: [{id, w, h}], edges: [{source, target}] in API direction. Type-mode `inherits` edges
 * point child -> parent, so they are reversed for layout to put parents on top; declaration
 * edges (container -> member) already point down.
 */
export function layeredPositions(dagre, nodes, edges, mode, opts = {}) {
  if (!HIERARCHY_MODES.includes(mode)) throw new Error(`unknown hierarchy mode: ${mode}`);
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 24, ranksep: 56, marginx: 20, marginy: 20, ...opts });
  g.setDefaultEdgeLabel(() => ({}));
  const ids = new Set(nodes.map((n) => n.id));
  for (const n of nodes) g.setNode(n.id, { width: n.w, height: n.h });
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue;
    if (mode === "type") g.setEdge(e.target, e.source);
    else g.setEdge(e.source, e.target);
  }
  dagre.layout(g);
  return Object.fromEntries(nodes.map((n) => {
    const { x, y } = g.node(n.id);
    return [n.id, { x, y }];
  }));
}
