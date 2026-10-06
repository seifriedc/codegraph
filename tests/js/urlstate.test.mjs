// URL view state: hash keys, caps, history decisions. Run: node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const load = (f) => import(path.join(here, "..", "..", "codegraph", "vis", "static", f));
const { parseHash, formatHash, DEFAULTS } = await load("state.js");
const { planChange, capState, notFoundMessage, MAX_EXPANDED } = await load("urlstate.js");

test("kind filters and stub expansions round-trip through the hash", () => {
  const s = { ...DEFAULTS, focus: "A", filters: { hiddenNodeKinds: ["file", "variable"], hiddenEdgeKinds: ["calls"] },
    stubs: ["stub:a:out:calls", "stub:a:out:calls"] };
  const h = formatHash(s);
  assert.match(h, /hideNodes=file%2Cvariable/);
  assert.match(h, /hideEdges=calls/);
  assert.deepEqual(parseHash(h), s);
  assert.equal(formatHash({ ...DEFAULTS, focus: "A" }), "#focus=A"); // defaults stay out of the URL
});

test("pan, zoom and positions are not part of the state", () => {
  assert.deepEqual(Object.keys(DEFAULTS).sort(), ["depth", "direction", "expanded", "externals", "filters",
    "groupBy", "kinds", "limit", "mode", "okinds", "stubs", "view"]);
});

const base = { ...DEFAULTS, focus: "A", view: "focus" };
const plan = (patch, from = base) => planChange(from, patch);

test("history: focus, view, mode and group-by push; the rest replace", () => {
  assert.equal(plan({ focus: "B" }).history, "push");
  assert.equal(plan({ view: "type" }).history, "push");
  assert.equal(plan({ mode: "impact" }).history, "push");
  assert.equal(plan({ groupBy: "package" }, { ...base, view: "overview", focus: null }).history, "push");
  for (const patch of [{ depth: 3 }, { direction: "in" }, { limit: 300 }, { externals: true }, { okinds: ["imports"] },
    { expanded: ["g"] }, { stubs: ["s"] }, { filters: { hiddenNodeKinds: ["file"], hiddenEdgeKinds: [] } }]) {
    assert.equal(plan(patch).history, "replace", JSON.stringify(patch));
  }
  assert.equal(plan({ depth: 2 }).history, "none"); // nothing changed
});

test("refetch only when the graph itself changes", () => {
  assert.equal(plan({ depth: 3 }).refetch, true);
  assert.equal(plan({ stubs: ["s"] }).refetch, false);
  assert.equal(plan({ filters: { hiddenNodeKinds: ["file"], hiddenEdgeKinds: [] } }).refetch, false);
});

test("a change that reloads the neighbourhood forgets stub expansions", () => {
  const from = { ...base, stubs: ["s1"] };
  for (const patch of [{ focus: "B" }, { depth: 3 }, { mode: "impact" }, { limit: 300 }, { view: "type" }, { direction: "in" }]) {
    assert.deepEqual(plan(patch, from).state.stubs, [], JSON.stringify(patch));
  }
  assert.deepEqual(plan({ filters: { hiddenNodeKinds: ["x"], hiddenEdgeKinds: [] } }, from).state.stubs, ["s1"]);
});

test("choosing a focus from the overview leaves the overview", () => {
  const p = planChange({ ...DEFAULTS, view: "overview", focus: null }, { focus: "A" });
  assert.equal(p.state.view, "focus");
  assert.equal(p.history, "push");
});

test("expanded and stub lists are capped with a notice", () => {
  const ids = Array.from({ length: MAX_EXPANDED + 7 }, (_, i) => "g" + i);
  const { state, notice } = capState({ ...DEFAULTS, expanded: ids, stubs: ["a"] });
  assert.equal(state.expanded.length, MAX_EXPANDED);
  assert.deepEqual(state.expanded, ids.slice(0, MAX_EXPANDED));
  assert.match(notice, /state truncated/i);
  assert.equal(capState({ ...DEFAULTS, stubs: ["a"] }).notice, null);
  const st = capState({ ...DEFAULTS, stubs: ids });
  assert.equal(st.state.stubs.length, MAX_EXPANDED);
  assert.match(st.notice, /state truncated/i);
});

test("node-not-found message names the node and mentions re-indexing", () => {
  assert.match(notFoundMessage("Circle::area"), /Circle::area.*re-indexed/);
});
