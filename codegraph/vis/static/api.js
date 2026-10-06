// Thin client for the JSON API (contract: codegraph/vis/models.py). No DOM.

async function getJson(url, fetchImpl) {
  const res = await fetchImpl(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

/** GET /api/neighborhood/{id}. Returns {focus, nodes, edges, truncated, total}, or null if the node is unknown. */
export function fetchNeighborhood(focus, { depth, direction, kinds, limit, mode } = {}, fetchImpl = fetch) {
  const p = new URLSearchParams();
  if (depth != null) p.set("depth", depth);
  if (direction) p.set("direction", direction);
  if (kinds && kinds.length) p.set("kinds", kinds.join(","));
  if (limit != null) p.set("limit", limit);
  if (mode) p.set("mode", mode); // "impact" | "dependencies" | "both": overrides direction and kinds
  const q = p.toString();
  return getJson(`/api/neighborhood/${encodeURIComponent(focus)}${q ? "?" + q : ""}`, fetchImpl);
}

/** GET /api/node/{id}. Returns the node detail, or null if the node is unknown. */
export function fetchNode(id, fetchImpl = fetch) {
  return getJson(`/api/node/${encodeURIComponent(id)}`, fetchImpl);
}

/** GET /api/search. filters: {kinds: [], languages: []}. Returns {nodes, total, truncated}. */
export function fetchSearch(q, { kinds, languages } = {}, fetchImpl = fetch) {
  const p = new URLSearchParams({ q });
  if (kinds && kinds.length) p.set("kinds", kinds.join(","));
  if (languages && languages.length) p.set("languages", languages.join(","));
  return getJson(`/api/search?${p}`, fetchImpl);
}
