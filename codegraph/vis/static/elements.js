// API response -> Cytoscape element definitions. Pure (no DOM, no Cytoscape import).
import { languageBadge } from "./style.js";

/** Short constant-size label: last segment of a qualified name ("Circle::area" -> "area"). */
export function shortLabel(node) {
  const q = node.qualified_name || node.name;
  if (node.kind === "file") return q.split("/").pop();
  const parts = q.split(/::|\./);
  return parts[parts.length - 1] || q;
}

/** Cytoscape elements for a neighborhood response; `data` carries everything the style needs. */
export function toElements(resp) {
  const ids = new Set(resp.nodes.map((n) => n.id));
  const nodes = resp.nodes.map((n) => ({
    group: "nodes",
    data: {
      id: n.id,
      label: shortLabel(n),
      full: n.qualified_name || n.name,
      kind: n.kind,
      language: n.language,
      badge: languageBadge(n.language),
      external: n.external,
      depth: n.depth,
      isFocus: n.id === resp.focus,
    },
  }));
  const edges = resp.edges
    .filter((e) => ids.has(e.source_id) && ids.has(e.target_id))
    .map((e) => ({
      group: "edges",
      data: { id: e.id, source: e.source_id, target: e.target_id, kind: e.kind },
    }));
  return { nodes, edges };
}

/** "Showing 150 of 1,204 nodes" status text; says when the view is truncated. */
export function statusText(resp) {
  const n = resp.nodes.length;
  const fmt = (x) => x.toLocaleString("en-US");
  return resp.truncated
    ? `Showing ${fmt(n)} of ${fmt(resp.total)} nodes (outer ring cut off)`
    : `Showing ${fmt(n)} node${n === 1 ? "" : "s"}`;
}
