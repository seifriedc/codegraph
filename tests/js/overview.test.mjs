// Unit tests for the pure Overview modules. Run outside pytest:  node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const load = (f) => import(path.join(here, "..", "..", "codegraph", "vis", "static", f));

const { parseHash, formatHash, DEFAULTS } = await load("state.js");
const { toOverviewElements, edgeWidth, edgeTooltip, toggleExpanded, overviewStatus } = await load("overview-elements.js");
const { fetchOverview } = await load("api.js");

test("view defaults: empty hash is the overview, a focus makes it the focus view", () => {
  assert.equal(parseHash("").view, "overview");
  assert.equal(parseHash("#focus=Shape").view, "focus");
  assert.equal(parseHash("#view=bogus").view, "overview");
  assert.equal(formatHash(parseHash("")), "");
  assert.equal(formatHash(parseHash("#focus=Shape")), "#focus=Shape");
});

test("overview state round-trips: expanded ids, kind override, group_by", () => {
  const s = { ...DEFAULTS, focus: null, view: "overview", expanded: ["dir:/a,b", "f-1"], okinds: ["calls", "imports"] };
  assert.deepEqual(parseHash(formatHash(s)), s);
  assert.deepEqual(parseHash("").expanded, []);
  assert.equal(parseHash("").okinds, null, "absent means server default (calls off)");
  assert.deepEqual(parseHash("#okinds=").okinds, [], "present-but-empty means no kinds");
  assert.equal(parseHash("").groupBy, "directory");
});

test("toggleExpanded adds and removes without mutating", () => {
  const a = ["x"];
  assert.deepEqual(toggleExpanded(a, "y"), ["x", "y"]);
  assert.deepEqual(toggleExpanded(a, "x"), []);
  assert.deepEqual(a, ["x"]);
});

test("edge width grows with log of count and is capped", () => {
  assert.ok(edgeWidth(1) < edgeWidth(10));
  assert.ok(edgeWidth(10) < edgeWidth(1000));
  assert.ok(edgeWidth(10) - edgeWidth(1) < 10 * (edgeWidth(2) - edgeWidth(1)), "sub-linear");
  assert.ok(edgeWidth(1e9) <= 14);
});

test("edge tooltip lists per-kind counts, biggest first", () => {
  assert.equal(edgeTooltip({ references: 1, calls: 12, imports: 3 }), "calls: 12, imports: 3, references: 1");
});

const resp = {
  nodes: [
    { id: "d", kind: "directory", name: "core", qualified_name: "core", group: true, parent: null, expanded: true, member_count: 5, node_id: null, external: false },
    { id: "f", kind: "file", name: "a.cpp", qualified_name: "core/a.cpp", group: true, parent: "d", expanded: false, member_count: 3, node_id: "f", external: false },
    { id: "m", kind: "function", name: "a1", qualified_name: "a1", group: false, parent: "d", expanded: false, member_count: 0, node_id: "m", external: false, language: "cpp" },
  ],
  edges: [
    { id: "agg:f>m", source_id: "f", target_id: "m", kinds: { calls: 2, imports: 1 }, count: 3 },
    { id: "agg:x", source_id: "f", target_id: "gone", kinds: { calls: 1 }, count: 1 },
  ],
  truncated: false, total: 3,
};

test("toOverviewElements builds compound parents and aggregate edges", () => {
  const { nodes, edges } = toOverviewElements(resp);
  const byId = Object.fromEntries(nodes.map((n) => [n.data.id, n.data]));
  assert.equal(byId.f.parent, "d");
  assert.equal(byId.d.parent, undefined, "top-level Groups have no parent key");
  assert.equal(byId.d.expanded, true);
  assert.equal(byId.f.group, true);
  assert.equal(byId.f.label, "a.cpp (3)", "collapsed Groups show their size");
  assert.equal(byId.d.label, "core", "expanded Groups are plain boxes");
  assert.equal(byId.m.label, "a1");
  assert.equal(edges.length, 1, "dangling edges are dropped");
  assert.equal(edges[0].data.aggregate, true);
  assert.equal(edges[0].data.tip, "calls: 2, imports: 1");
  assert.equal(edges[0].data.w, edgeWidth(3));
});

test("overviewStatus", () => {
  assert.equal(overviewStatus({ nodes: resp.nodes, edges: resp.edges, kinds: ["imports"] }),
    "Overview: 2 groups, 1 members, 2 aggregate edges (imports)");
  assert.match(overviewStatus({ nodes: [], edges: [], kinds: [] }), /no edge kinds/);
  const cut = overviewStatus({ nodes: resp.nodes, edges: resp.edges, kinds: ["imports"], truncated: true, total: 412 });
  assert.match(cut, /members capped: showing 1 of 410 /);
});

test("fetchOverview sends expanded ids as repeated params and an explicit kind list", async () => {
  let seen;
  const f = async (u) => { seen = u; return { status: 200, ok: true, json: async () => ({ ok: 1 }) }; };
  await fetchOverview({ expanded: ["a", "b c"], kinds: ["imports"], groupBy: "directory" }, f);
  assert.equal(seen, "/api/overview?group_by=directory&expanded=a&expanded=b+c&kinds=imports");
  await fetchOverview({ kinds: [] }, f);
  assert.equal(seen, "/api/overview?kinds=");
  await fetchOverview({}, f);
  assert.equal(seen, "/api/overview");
});

test("every view value round-trips through parseHash/formatHash", async () => {
  const { parseHash, formatHash, VIEWS } = await import("../../codegraph/vis/static/state.js");
  assert.deepEqual([...VIEWS].sort(), ["declaration", "focus", "overview", "type"]);
  for (const view of VIEWS) for (const focus of [null, "Shape"]) {
    const s = { ...parseHash(""), focus, view };
    const back = parseHash(formatHash(s));
    assert.equal(back.view, view);
    assert.equal(back.focus, focus);
  }
});

test("group_by 'package' and the externals toggle round-trip through the hash", () => {
  const s = { ...DEFAULTS, focus: null, view: "overview", groupBy: "package", externals: true, expanded: ["p-1"] };
  assert.equal(formatHash(s), "#expanded=p-1&groupby=package&externals=1");
  assert.deepEqual(parseHash(formatHash(s)), s);
  assert.equal(parseHash("#groupby=galaxy").groupBy, "directory", "unknown value falls back");
  assert.equal(parseHash("").externals, false, "externals are hidden by default");
  assert.equal(formatHash({ ...DEFAULTS, focus: null, view: "overview" }), "");
});

test("fetchOverview sends group_by and externals", async () => {
  let url;
  const fake = async (u) => { url = u; return { ok: true, status: 200, json: async () => ({}) }; };
  await fetchOverview({ groupBy: "package", externals: true }, fake);
  assert.equal(url, "/api/overview?group_by=package&externals=true");
});
