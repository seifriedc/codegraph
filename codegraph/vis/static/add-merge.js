// Shift-Enter "add to canvas": merge a freshly fetched neighborhood into the current focus view. Pure.
import { mergeGraphs } from "./search.js";

/**
 * Union of the current view and `added` (nodes, edges and Stub nodes by id; the current focus stays).
 * Returns {merged, newIds}: the merged graph response and the ids of nodes that were not on screen before.
 */
export function mergeAdded(current, added) {
  const merged = mergeGraphs(current, added);
  const seen = new Set((current.stubs || []).map((s) => s.id));
  merged.stubs = [...(current.stubs || []), ...(added.stubs || []).filter((s) => !seen.has(s.id))];
  const before = new Set(current.nodes.map((n) => n.id));
  return { merged, newIds: merged.nodes.filter((n) => !before.has(n.id)).map((n) => n.id) };
}
