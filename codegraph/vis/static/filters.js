// Kind-filter state: which node kinds and edge kinds are hidden. Pure (no DOM); immutable updates.
// Consumers: legend UI, canvas visibility, the API `kinds` param, URL state and search chips.
// Node-kind filtering is client-side only; edge-kind filtering is client-side AND sent as `kinds` (edge kinds).
import { EDGE_KINDS } from "./style.js";

export function defaultFilters() {
  return { hiddenNodeKinds: [], hiddenEdgeKinds: [] };
}

const toggle = (list, kind) => (list.includes(kind) ? list.filter((k) => k !== kind) : [...list, kind].sort());

export const toggleNodeKind = (f, kind) => ({ ...f, hiddenNodeKinds: toggle(f.hiddenNodeKinds, kind) });
export const toggleEdgeKind = (f, kind) => ({ ...f, hiddenEdgeKinds: toggle(f.hiddenEdgeKinds, kind) });

export const isNodeKindVisible = (f, kind) => !f.hiddenNodeKinds.includes(kind);
export const isEdgeKindVisible = (f, kind) => !f.hiddenEdgeKinds.includes(kind);

/** Node data ({kind, isFocus}); the Focus node is never hidden. */
export const isNodeVisible = (f, node) => !!node.isFocus || isNodeKindVisible(f, node.kind);

/** Edge data plus its endpoint data: hidden when its kind or either endpoint is hidden. */
export function isEdgeVisible(f, edge, source, target) {
  return isEdgeKindVisible(f, edge.kind) && isNodeVisible(f, source) && isNodeVisible(f, target);
}

/** Value for the API `kinds` param: undefined (no restriction) unless an edge kind is hidden. */
export function edgeKindsParam(f) {
  return f.hiddenEdgeKinds.length ? EDGE_KINDS.filter((k) => isEdgeKindVisible(f, k)) : undefined;
}

/** Plain string params for the URL-state module: {hideNodes?, hideEdges?} (comma-separated). */
export function filtersToParams(f) {
  const p = {};
  if (f.hiddenNodeKinds.length) p.hideNodes = f.hiddenNodeKinds.join(",");
  if (f.hiddenEdgeKinds.length) p.hideEdges = f.hiddenEdgeKinds.join(",");
  return p;
}

const split = (s) => (s ? s.split(",").filter(Boolean).sort() : []);

export function filtersFromParams(p = {}) {
  return { hiddenNodeKinds: split(p.hideNodes), hiddenEdgeKinds: split(p.hideEdges) };
}
