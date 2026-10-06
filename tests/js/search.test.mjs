// Pure search/recent modules. Run:  node --test tests/js/*.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const load = (f) => import(path.join(here, "..", "..", "codegraph", "vis", "static", f));

const { createSearchModel, resultRow, isFocusShortcut, mergeGraphs, MIN_CHARS, DEBOUNCE_MS } = await load("search.js");
const { createRecent, RECENT_MAX } = await load("recent.js");
const { fetchSearch } = await load("api.js");

// ---- fakes ----
function fakeTimers() {
  let now = 0, next = 1;
  const pending = new Map();
  return {
    setTimer: (fn, ms) => { const id = next++; pending.set(id, { fn, at: now + ms }); return id; },
    clearTimer: (id) => pending.delete(id),
    advance(ms) {
      now += ms;
      for (const [id, t] of [...pending]) if (t.at <= now) { pending.delete(id); t.fn(); }
    },
  };
}
const hit = (id, extra = {}) => ({
  id, kind: "class", name: id, qualified_name: id, path: "a/b.cpp", language: "cpp", more_paths: 0, ...extra,
});
function setup(responses = {}) {
  const t = fakeTimers();
  const calls = [];
  const fetchFn = async (q, filters) => {
    calls.push({ q, filters });
    return responses[q] ?? { nodes: [], total: 0, truncated: false };
  };
  const model = createSearchModel({ fetchFn, setTimer: t.setTimer, clearTimer: t.clearTimer });
  return { t, calls, model };
}
const flush = () => new Promise((r) => setImmediate(r));

// ---- type-ahead ----
test("no request below the minimum length; 2 chars after the debounce fires one", async () => {
  const { t, calls, model } = setup();
  assert.equal(MIN_CHARS, 2);
  assert.equal(DEBOUNCE_MS, 150);
  model.setQuery("S");
  t.advance(500);
  assert.equal(calls.length, 0);
  model.setQuery("Sh");
  t.advance(DEBOUNCE_MS - 1);
  assert.equal(calls.length, 0);
  t.advance(1);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].q, "Sh");
});

test("typing resets the debounce: only the last query is sent", async () => {
  const { t, calls, model } = setup();
  model.setQuery("Sh"); t.advance(100);
  model.setQuery("Sha"); t.advance(100);
  assert.equal(calls.length, 0);
  t.advance(50);
  assert.deepEqual(calls.map((c) => c.q), ["Sha"]);
});

test("results land in state, selection starts on the first row", async () => {
  const { t, model } = setup({ Sh: { nodes: [hit("A"), hit("B")], total: 2, truncated: false } });
  model.setQuery("Sh"); t.advance(150); await flush();
  const s = model.state();
  assert.deepEqual(s.results.map((r) => r.id), ["A", "B"]);
  assert.equal(s.selected, 0);
  assert.equal(s.total, 2);
});

test("a slow stale response never overwrites a newer one", async () => {
  const t = fakeTimers();
  const resolvers = {};
  const fetchFn = (q) => new Promise((res) => { resolvers[q] = res; });
  const model = createSearchModel({ fetchFn, setTimer: t.setTimer, clearTimer: t.clearTimer });
  model.setQuery("Sh"); t.advance(150);
  model.setQuery("Sha"); t.advance(150);
  resolvers["Sha"]({ nodes: [hit("New")], total: 1, truncated: false });
  await flush();
  resolvers["Sh"]({ nodes: [hit("Old")], total: 1, truncated: false });
  await flush();
  assert.deepEqual(model.state().results.map((r) => r.id), ["New"]);
});

test("clearing the query below the minimum clears results and cancels pending search", async () => {
  const { t, calls, model } = setup({ Sh: { nodes: [hit("A")], total: 1, truncated: false } });
  model.setQuery("Sh"); t.advance(150); await flush();
  model.setQuery("S");
  assert.deepEqual(model.state().results, []);
  model.setQuery("Sh"); model.setQuery("");
  t.advance(1000);
  assert.equal(calls.length, 1);
});

test("a failed fetch is reported as error state, not thrown", async () => {
  const t = fakeTimers();
  const model = createSearchModel({
    fetchFn: async () => { throw new Error("boom"); }, setTimer: t.setTimer, clearTimer: t.clearTimer,
  });
  model.setQuery("Sh"); t.advance(150); await flush();
  assert.equal(model.state().error, "boom");
});

test("changing a filter re-queries (debounced) with the chips' values", async () => {
  const { t, calls, model } = setup();
  model.setQuery("Sh"); t.advance(150);
  model.setFilters({ kinds: ["class"], languages: ["cpp"] }); t.advance(150);
  assert.deepEqual(calls[1].filters, { kinds: ["class"], languages: ["cpp"] });
});

// ---- keyboard ----
test("arrows move the selection and clamp at both ends", async () => {
  const { t, model } = setup({ Sh: { nodes: [hit("A"), hit("B"), hit("C")], total: 3, truncated: false } });
  model.setQuery("Sh"); t.advance(150); await flush();
  model.key({ key: "ArrowDown" });
  model.key({ key: "ArrowDown" });
  model.key({ key: "ArrowDown" });
  assert.equal(model.state().selected, 2);
  model.key({ key: "ArrowUp" });
  assert.equal(model.state().selected, 1);
  model.key({ key: "ArrowUp" }); model.key({ key: "ArrowUp" });
  assert.equal(model.state().selected, 0);
});

test("Enter replaces the focus; Shift-Enter adds to the canvas", async () => {
  const { t, model } = setup({ Sh: { nodes: [hit("A"), hit("B")], total: 2, truncated: false } });
  model.setQuery("Sh"); t.advance(150); await flush();
  model.key({ key: "ArrowDown" });
  assert.deepEqual(model.key({ key: "Enter" }), { type: "focus", node: hit("B") });
  assert.deepEqual(model.key({ key: "Enter", shiftKey: true }), { type: "add", node: hit("B") });
});

test("Enter with no results does nothing", () => {
  const { model } = setup();
  assert.equal(model.key({ key: "Enter" }), null);
});

test("Escape clears the query and results, and asks to blur", async () => {
  const { t, model } = setup({ Sh: { nodes: [hit("A")], total: 1, truncated: false } });
  model.setQuery("Sh"); t.advance(150); await flush();
  assert.deepEqual(model.key({ key: "Escape" }), { type: "close" });
  assert.equal(model.state().query, "");
  assert.deepEqual(model.state().results, []);
});

test("/ and Ctrl-K (or Cmd-K) focus the box, but not while typing in a field", () => {
  assert.equal(isFocusShortcut({ key: "/" }, "DIV"), true);
  assert.equal(isFocusShortcut({ key: "k", ctrlKey: true }, "BODY"), true);
  assert.equal(isFocusShortcut({ key: "k", metaKey: true }, "BODY"), true);
  assert.equal(isFocusShortcut({ key: "/" }, "INPUT"), false);
  assert.equal(isFocusShortcut({ key: "/" }, "TEXTAREA"), false);
  assert.equal(isFocusShortcut({ key: "k" }, "BODY"), false);
  // Ctrl-K still works from inside the box (browser default is address bar / emacs kill-line)
  assert.equal(isFocusShortcut({ key: "k", ctrlKey: true }, "INPUT"), true);
});

// ---- result rows ----
test("result row: short name, qualified name, kind, language badge, path with +N more", () => {
  const row = resultRow(hit("x", {
    kind: "method", name: "area", qualified_name: "Circle::area", path: "cpp/shapes.cpp", more_paths: 2,
  }));
  assert.equal(row.shortName, "area");
  assert.equal(row.qualifiedName, "Circle::area");
  assert.equal(row.kind, "method");
  assert.equal(row.language, "cpp");
  assert.equal(row.pathText, "cpp/shapes.cpp +2 more");
});

test("result row: external nodes have no path; no +N when only one file", () => {
  assert.equal(resultRow(hit("x", { path: null, external: true })).pathText, "external");
  assert.equal(resultRow(hit("x", { path: "a.c", more_paths: 0 })).pathText, "a.c");
});

test("results note says when the list is truncated", async () => {
  const { t, model } = setup({ Sh: { nodes: [hit("A")], total: 57, truncated: true } });
  model.setQuery("Sh"); t.advance(150); await flush();
  assert.match(model.state().note, /1 of 57/);
});

// ---- merge (Shift-Enter) ----
test("mergeGraphs unions nodes and edges by id and keeps the current focus", () => {
  const cur = { focus: "A", nodes: [{ id: "A", depth: 0 }, { id: "B", depth: 1 }], edges: [{ id: "e1" }], truncated: false, total: 2 };
  const add = { focus: "C", nodes: [{ id: "C", depth: 0 }, { id: "B", depth: 1 }], edges: [{ id: "e1" }, { id: "e2" }], truncated: true, total: 9 };
  const m = mergeGraphs(cur, add);
  assert.equal(m.focus, "A");
  assert.deepEqual(m.nodes.map((n) => n.id), ["A", "B", "C"]);
  assert.deepEqual(m.edges.map((e) => e.id), ["e1", "e2"]);
  assert.equal(m.truncated, true);
  assert.equal(mergeGraphs(null, add), add);
});

// ---- recent nodes ----
function memStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => void m.set(k, String(v)) };
}
const brokenStorage = {
  getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); },
};

test("recent: most recent first, deduped, capped at 10, persisted", () => {
  const store = memStorage();
  const r = createRecent(store);
  assert.equal(RECENT_MAX, 10);
  for (let i = 0; i < 12; i++) r.add(hit(`n${i}`));
  r.add(hit("n5"));
  const ids = r.list().map((n) => n.id);
  assert.equal(ids.length, 10);
  assert.equal(ids[0], "n5");
  assert.equal(new Set(ids).size, 10);
  assert.deepEqual(createRecent(store).list().map((n) => n.id), ids); // survives a reload
});

test("recent: tolerates unavailable storage (get/set throw) and keeps working in memory", () => {
  const r = createRecent(brokenStorage);
  assert.deepEqual(r.list(), []);
  r.add(hit("A"));
  assert.deepEqual(r.list().map((n) => n.id), ["A"]);
});

test("recent: tolerates no storage at all and corrupt stored data", () => {
  assert.deepEqual(createRecent(undefined).list(), []);
  const s = memStorage();
  s.setItem("codegraph.recent", "{not json");
  assert.deepEqual(createRecent(s).list(), []);
  s.setItem("codegraph.recent", JSON.stringify({ not: "an array" }));
  assert.deepEqual(createRecent(s).list(), []);
});

test("recent: stores only what a row needs, not the whole response", () => {
  const store = memStorage();
  createRecent(store).add({ ...hit("A"), line_start: 3, depth: 4 });
  const saved = JSON.parse(store.getItem("codegraph.recent"))[0];
  assert.deepEqual(Object.keys(saved).sort(),
    ["external", "id", "kind", "language", "more_paths", "name", "path", "qualified_name"].sort());
});

// ---- api ----
test("fetchSearch builds the query string with filters", async () => {
  let url;
  const f = async (u) => { url = u; return { ok: true, status: 200, json: async () => ({ nodes: [] }) }; };
  await fetchSearch("Sh ape", { kinds: ["class", "type"], languages: ["cpp"] }, f);
  assert.equal(url, "/api/search?q=Sh+ape&kinds=class%2Ctype&languages=cpp");
  await fetchSearch("ab", {}, f);
  assert.equal(url, "/api/search?q=ab");
});
