// Scale policy, client side. Pure (no DOM, no Cytoscape): the node budget, the accumulated graph
// (focus neighbourhood + expansions, with per-expansion undo and prune) and Stub node elements.
// The server enforces the same numbers (codegraph/vis/focus.py); the client re-checks them.

export const BUDGET = Object.freeze({ defaultLimit: 150, maxLimit: 500, warnAt: 300, fanOut: 15 });

/** Clamp a user-supplied node limit to [1, maxLimit]; junk gives the default. */
export function clampLimit(n, budget = BUDGET) {
  if (!Number.isFinite(n)) return budget.defaultLimit;
  return Math.min(budget.maxLimit, Math.max(1, Math.trunc(n)));
}

/** The "raise limit" step: double, up to the server maximum. */
export function nextLimit(cur, budget = BUDGET) {
  return Math.min(budget.maxLimit, cur * 2);
}

/** "+185 calls in": hidden count, edge kind, direction relative to the owner. */
export function stubLabel(s) {
  return `+${s.hidden} ${s.kind} ${s.direction}`;
}

/** Cytoscape elements for Stub nodes: a node plus a connecting edge from its owner. Pure data. */
export function stubElements(stubs, presentIds) {
  const nodes = [], edges = [];
  for (const s of stubs) {
    if (!presentIds.has(s.owner)) continue;
    nodes.push({
      group: "nodes",
      data: { id: s.id, label: stubLabel(s), full: stubLabel(s), kind: "stub", isStub: true,
              owner: s.owner, edgeKind: s.kind, direction: s.direction, hidden: s.hidden, offset: s.offset },
    });
    edges.push({ group: "edges", data: { id: "edge:" + s.id, source: s.owner, target: s.id, kind: "stub", isStubEdge: true } });
  }
  return { nodes, edges };
}

/** Status line text. `shown`/`total` count real nodes (Stub nodes excluded). */
export function scaleStatus({ shown, total, truncated, expanded = false }) {
  const fmt = (x) => x.toLocaleString("en-US");
  if (truncated) return `Showing ${fmt(shown)} of ${fmt(total)} nodes (outer ring cut off)`;
  return `Showing ${fmt(shown)} node${shown === 1 ? "" : "s"}${expanded ? " (expanded)" : ""}`;
}

/**
 * The accumulated view: the base neighborhood response plus a stack of expansions.
 * reset(resp) starts over; expand(stubId, page) merges a /api/expand page; undo() reverts the
 * last expansion; prune() drops all expansions. view() is a neighborhood-shaped response.
 */
export function createModel(budget = BUDGET) {
  let baseResp = null, focus = null;
  let nodes = new Map(), edges = new Map(), stubs = new Map();
  let history = [];

  function load(resp) {
    focus = resp.focus;
    nodes = new Map(resp.nodes.map((n) => [n.id, n]));
    edges = new Map(resp.edges.map((e) => [e.id, e]));
    stubs = new Map((resp.stubs || []).map((s) => [s.id, s]));
    history = [];
  }

  return {
    reset(resp) { baseResp = structuredClone(resp); load(baseResp); },
    get size() { return nodes.size; },
    focus: () => focus,
    canUndo: () => history.length > 0,
    overWarning: () => nodes.size >= budget.warnAt,
    view: () => ({ focus, nodes: [...nodes.values()], edges: [...edges.values()], stubs: [...stubs.values()] }),

    /** Merge one page for the stub `stubId`. Returns {added: [node ids], budgetHit}. */
    expand(stubId, pageResp) {
      const old = stubs.get(stubId);
      if (!old) return { added: [], budgetHit: false };
      const owner = nodes.get(pageResp.owner);
      const depth = (owner && owner.depth != null ? owner.depth : 0) + 1;
      const entry = { stubId, oldStub: old, addedNodes: [], addedEdges: [], addedStub: null };
      let consumed = pageResp.nodes.length, budgetHit = false;
      pageResp.nodes.forEach((n, i) => {
        if (nodes.has(n.id)) return;
        if (nodes.size >= budget.maxLimit) {
          if (!budgetHit) consumed = i;
          budgetHit = true;
          return;
        }
        nodes.set(n.id, { ...n, depth });
        entry.addedNodes.push(n.id);
      });
      for (const e of pageResp.edges) {
        if (!edges.has(e.id) && nodes.has(e.source_id) && nodes.has(e.target_id)) {
          edges.set(e.id, e);
          entry.addedEdges.push(e.id);
        }
      }
      stubs.delete(stubId);
      let next = null;
      if (budgetHit) next = { ...old, hidden: old.hidden - consumed, offset: old.offset + consumed };
      else if (pageResp.stub) next = pageResp.stub;
      if (next) { stubs.set(next.id, next); entry.addedStub = next.id; }
      history.push(entry);
      return { added: [...entry.addedNodes], budgetHit };
    },

    undo() {
      const h = history.pop();
      if (!h) return false;
      for (const id of h.addedNodes) nodes.delete(id);
      for (const id of h.addedEdges) edges.delete(id);
      if (h.addedStub) stubs.delete(h.addedStub);
      stubs.set(h.oldStub.id, h.oldStub);
      return true;
    },

    /** Back to the focus neighbourhood the view started with; expansions are forgotten. */
    prune() { if (baseResp) load(structuredClone(baseResp)); },
  };
}
