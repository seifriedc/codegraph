// Thin client for the JSON API (contract: codegraph/vis/models.py). No DOM.

async function getJson(url, fetchImpl) {
  const res = await fetchImpl(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

/** GET /api/neighborhood/{id}. Returns {focus, nodes, edges, truncated, total}, or null if the node is unknown. */
export function fetchNeighborhood(focus, { depth, direction, kinds, limit, mode, perNodeCap } = {}, fetchImpl = fetch) {
  const p = new URLSearchParams();
  if (depth != null) p.set("depth", depth);
  if (direction) p.set("direction", direction);
  if (kinds && kinds.length) p.set("kinds", kinds.join(","));
  if (limit != null) p.set("limit", limit);
  if (perNodeCap != null) p.set("per_node_cap", perNodeCap);
  if (mode) p.set("mode", mode); // "neighborhood" honours direction and kinds; "impact" | "dependencies" | "both" ignore them
  const q = p.toString();
  return getJson(`/api/neighborhood/${encodeURIComponent(focus)}${q ? "?" + q : ""}`, fetchImpl);
}

/**
 * GET /api/overview. `expanded` are Group ids from the previous response (the server keeps no state).
 * `kinds`: undefined/null = server default (calls off); an array, even empty, is explicit.
 */
export function fetchOverview({ groupBy, expanded, kinds, externals } = {}, fetchImpl = fetch) {
  const p = new URLSearchParams();
  if (groupBy) p.set("group_by", groupBy);
  for (const id of expanded || []) p.append("expanded", id);
  if (kinds != null) p.set("kinds", kinds.join(","));
  if (externals != null) p.set("externals", String(externals));
  const q = p.toString();
  return getJson(`/api/overview${q ? "?" + q : ""}`, fetchImpl);
}

/** GET /api/hierarchy/{id}?mode=type|declaration. Same response shape as neighborhood; null if unknown. */
export function fetchHierarchy(focus, { mode, limit } = {}, fetchImpl = fetch) {
  const p = new URLSearchParams({ mode });
  if (limit != null) p.set("limit", limit);
  return getJson(`/api/hierarchy/${encodeURIComponent(focus)}?${p}`, fetchImpl);
}

/** GET /api/node/{id}. Returns the node detail, or null if the node is unknown. */
export function fetchNode(id, fetchImpl = fetch) {
  return getJson(`/api/node/${encodeURIComponent(id)}`, fetchImpl);
}

/** GET /api/expand/{owner}: the next page of a Stub node's hidden neighbors, or null if the owner is unknown. */
export function fetchExpand(stub, fetchImpl = fetch, pageSize = 15) {
  const p = new URLSearchParams({ direction: stub.direction, kind: stub.kind, offset: stub.offset, limit: pageSize });
  return getJson(`/api/expand/${encodeURIComponent(stub.owner)}?${p}`, fetchImpl);
}

/** GET /api/search. filters: {kinds: [], languages: []}. Returns {nodes, total, truncated}. */
export function fetchSearch(q, { kinds, languages } = {}, fetchImpl = fetch) {
  const p = new URLSearchParams({ q });
  if (kinds && kinds.length) p.set("kinds", kinds.join(","));
  if (languages && languages.length) p.set("languages", languages.join(","));
  return getJson(`/api/search?${p}`, fetchImpl);
}
