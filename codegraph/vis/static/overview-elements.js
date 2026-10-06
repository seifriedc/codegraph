// Overview API response -> Cytoscape elements. Pure (no DOM, no Cytoscape import).

/** Aggregate edge thickness: grows with log(count), capped. */
export function edgeWidth(count) {
  return Math.min(14, 1.5 + 1.6 * Math.log(Math.max(1, count)));
}

/** "calls: 12, imports: 3": per-kind counts, biggest first (ties by kind). */
export function edgeTooltip(kinds) {
  return Object.entries(kinds)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([k, n]) => `${k}: ${n}`)
    .join(", ");
}

/** New expanded list with `id` added, or removed if present. */
export function toggleExpanded(expanded, id) {
  return expanded.includes(id) ? expanded.filter((x) => x !== id) : [...expanded, id];
}

/** Compound parents + Aggregate edges. Collapsed Groups carry their size in the label. */
export function toOverviewElements(resp) {
  const ids = new Set(resp.nodes.map((n) => n.id));
  const nodes = resp.nodes.map((n) => {
    const data = {
      id: n.id,
      label: n.group && !n.expanded && n.member_count ? `${n.name} (${n.member_count})` : n.name,
      full: n.qualified_name || n.name,
      kind: n.kind,
      language: n.language,
      external: n.external,
      group: n.group,
      expanded: n.expanded,
      memberCount: n.member_count,
      nodeId: n.node_id,
    };
    if (n.parent) data.parent = n.parent;
    return { group: "nodes", data };
  });
  const edges = resp.edges
    .filter((e) => ids.has(e.source_id) && ids.has(e.target_id))
    .map((e) => ({
      group: "edges",
      data: {
        id: e.id, source: e.source_id, target: e.target_id, aggregate: true,
        count: e.count, kinds: e.kinds, tip: edgeTooltip(e.kinds), w: edgeWidth(e.count),
      },
    }));
  return { nodes, edges };
}

/** Status line for the overview. */
export function overviewStatus(resp) {
  const groups = resp.nodes.filter((n) => n.group).length;
  const members = resp.nodes.length - groups;
  const kinds = resp.kinds.length ? ` (${resp.kinds.join(", ")})` : " (no edge kinds selected)";
  // `total` counts Groups and members; only members are ever capped by the server
  const capped = resp.truncated ? `; members capped: showing ${members} of ${resp.total - groups} (collapse a Group to see the rest)` : "";
  return `Overview: ${groups} groups, ${members} members, ${resp.edges.length} aggregate edges${kinds}${capped}`;
}
