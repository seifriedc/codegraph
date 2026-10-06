// Unit tests for the pure scale-policy modules (budget, accumulated graph with undo, stub elements).
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const staticDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "codegraph", "vis", "static");
const { BUDGET, clampLimit, nextLimit, createModel, stubLabel, stubElements, scaleStatus } =
  await import(path.join(staticDir, "scale.js"));
const { parseHash, formatHash, DEFAULTS } = await import(path.join(staticDir, "state.js"));
const { fetchNeighborhood, fetchExpand } = await import(path.join(staticDir, "api.js"));

const node = (id, depth = 1) => ({ id, kind: "function", name: id, qualified_name: id, depth, external: false, language: "cpp" });
const stub = (owner, hidden, offset) => ({ id: `stub:${owner}:in:calls`, owner, direction: "in", kind: "calls", hidden, offset });
const base = () => ({
  focus: "f", nodes: [node("f", 0), node("a"), node("b")],
  edges: [{ id: "e1", kind: "calls", source_id: "a", target_id: "f" }, { id: "e2", kind: "calls", source_id: "b", target_id: "f" }],
  stubs: [stub("f", 5, 2)], truncated: false, total: 3,
});
const page = (names, next) => ({
  owner: "f", nodes: names.map((n) => node(n)),
  edges: names.map((n, i) => ({ id: "x" + n, kind: "calls", source_id: n, target_id: "f" })),
  stub: next, total: 7,
});

test("budget numbers follow the scale policy", () => {
  assert.deepEqual(BUDGET, { defaultLimit: 150, maxLimit: 500, warnAt: 300, fanOut: 15 });
  assert.equal(clampLimit(9999), 500);
  assert.equal(clampLimit(-3), 1);
  assert.equal(clampLimit(NaN), 150);
  assert.equal(nextLimit(150), 300);
  assert.equal(nextLimit(300), 500);
  assert.equal(nextLimit(500), 500);
});

test("limit round-trips through the URL hash and is clamped", () => {
  assert.equal(parseHash("#focus=x&limit=300").limit, 300);
  assert.equal(parseHash("#focus=x").limit, 150);
  assert.equal(parseHash("#focus=x&limit=100000").limit, 500);
  assert.equal(formatHash({ focus: "x", ...DEFAULTS }), "#focus=x");
  assert.equal(formatHash({ focus: "x", ...DEFAULTS, limit: 300 }), "#focus=x&limit=300");
});

test("api: limit and per_node_cap are sent, and fetchExpand builds its query", async () => {
  let seen;
  const f = async (u) => { seen = u; return { status: 404 }; };
  await fetchNeighborhood("a", { limit: 300, perNodeCap: 5 }, f);
  assert.equal(seen, "/api/neighborhood/a?limit=300&per_node_cap=5");
  assert.equal(await fetchExpand({ id: "stub:f:in:calls", owner: "f", direction: "in", kind: "calls", offset: 15 }, f), null);
  assert.equal(seen, "/api/expand/f?direction=in&kind=calls&offset=15&limit=15");
});

test("expanding a stub merges nodes, swaps the stub for its continuation and reports what is new", () => {
  const m = createModel();
  m.reset(base());
  const r = m.expand("stub:f:in:calls", page(["c", "d"], stub("f", 3, 4)));
  assert.deepEqual(r.added.sort(), ["c", "d"]);
  const v = m.view();
  assert.deepEqual(v.nodes.map((n) => n.id).sort(), ["a", "b", "c", "d", "f"]);
  assert.deepEqual(v.stubs.map((s) => [s.id, s.hidden, s.offset]), [["stub:f:in:calls", 3, 4]]);
  assert.equal(v.nodes.find((n) => n.id === "c").depth, 1);
  assert.equal(m.size, 5);
});

test("expansion skips nodes already shown and the last page removes the stub", () => {
  const m = createModel();
  m.reset(base());
  const r = m.expand("stub:f:in:calls", page(["a", "c"], null));
  assert.deepEqual(r.added, ["c"]);
  assert.deepEqual(m.view().stubs, []);
});

test("undo reverts the last expansion exactly, one at a time", () => {
  const m = createModel();
  m.reset(base());
  const before = JSON.stringify(m.view());
  m.expand("stub:f:in:calls", page(["c", "d"], stub("f", 3, 4)));
  m.expand("stub:f:in:calls", page(["e"], null));
  assert.equal(m.canUndo(), true);
  m.undo();
  assert.equal(m.size, 5);
  assert.deepEqual(m.view().stubs.map((s) => s.hidden), [3]);
  m.undo();
  assert.equal(JSON.stringify(m.view()), before);
  assert.equal(m.canUndo(), false);
  assert.equal(m.undo(), false);
});

test("the client enforces the node budget on expansion and keeps a stub for what was dropped", () => {
  const m = createModel({ ...BUDGET, maxLimit: 5, warnAt: 4 });
  m.reset(base());
  const r = m.expand("stub:f:in:calls", page(["c", "d", "e", "g"], null));
  assert.deepEqual(r.added, ["c", "d"]);
  assert.equal(r.budgetHit, true);
  assert.equal(m.size, 5);
  assert.deepEqual(m.view().stubs.map((s) => [s.hidden, s.offset]), [[3, 4]]);
  m.undo();
  assert.equal(m.size, 3);
  assert.deepEqual(m.view().stubs.map((s) => [s.hidden, s.offset]), [[5, 2]]);
});

test("warning at the threshold and prune back to the focus neighborhood", () => {
  const m = createModel({ ...BUDGET, warnAt: 4 });
  m.reset(base());
  assert.equal(m.overWarning(), false);
  m.expand("stub:f:in:calls", page(["c", "d"], null));
  assert.equal(m.overWarning(), true);
  m.prune();
  assert.equal(m.size, 3);
  assert.equal(m.canUndo(), false);
  assert.equal(m.overWarning(), false);
  assert.deepEqual(m.view().stubs.map((s) => s.id), ["stub:f:in:calls"]);
});

test("stub elements: labelled node plus a connecting edge, flagged for styling", () => {
  assert.equal(stubLabel(stub("f", 185, 15)), "+185 calls in");
  assert.equal(stubLabel({ ...stub("f", 3, 15), direction: "out" }), "+3 calls out");
  const { nodes, edges } = stubElements([stub("f", 5, 2)], new Set(["f"]));
  assert.equal(nodes[0].data.isStub, true);
  assert.equal(nodes[0].data.label, "+5 calls in");
  assert.equal(nodes[0].data.owner, "f");
  assert.deepEqual([edges[0].data.source, edges[0].data.target], ["f", "stub:f:in:calls"]);
  assert.deepEqual(stubElements([stub("zz", 1, 1)], new Set(["f"])), { nodes: [], edges: [] });
});

test("status line reports totals, truncation, stubs and the 300-node warning", () => {
  const b = base();
  assert.equal(scaleStatus({ shown: 3, total: 3, truncated: false }), "Showing 3 nodes");
  assert.match(scaleStatus({ shown: 150, total: 1204, truncated: true }), /150 of 1,204.*outer ring/);
  assert.match(scaleStatus({ shown: 320, total: 320, truncated: false, expanded: true }), /320 nodes \(expanded\)/);
});

test("adopt replaces the accumulated graph with a merged one, trimming to the budget and dropping orphan stubs", () => {
  const m = createModel({ ...BUDGET, maxLimit: 4 });
  m.reset(base());
  m.expand("stub:f:in:calls", page(["c"], null));
  const merged = {
    focus: "f", nodes: [node("f", 0), node("a"), node("b"), node("c"), node("z")],
    edges: [{ id: "e1", kind: "calls", source_id: "a", target_id: "f" }, { id: "ez", kind: "calls", source_id: "z", target_id: "f" }],
    stubs: [stub("z", 2, 1), stub("f", 1, 1)],
  };
  const r = m.adopt(merged);
  assert.equal(m.size, 4);
  assert.deepEqual(r.dropped, 1);
  assert.deepEqual(m.view().edges.map((e) => e.id), ["e1"]);
  assert.deepEqual(m.view().stubs.map((s) => s.owner), ["f"]);
  assert.equal(m.canUndo(), false);
  m.prune();
  assert.equal(m.size, 4, "the adopted graph is the new base");
});
