// Visual encoding, filters and legend: pure decisions, run with node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const load = (f) => import(path.join(here, "..", "..", "codegraph", "vis", "static", f));

const style = await load("style.js");
const filters = await load("filters.js");
const legend = await load("legend.js");
const { toElements } = await load("elements.js");

const NODE_KINDS = ["file", "module", "package", "function", "class", "method", "type", "variable"];
const EDGE_KINDS = ["imports", "calls", "defines", "contains", "inherits", "references", "instantiates"];

test("every node kind has a distinct shape and a tint (readable without colour)", () => {
  const shapes = NODE_KINDS.map((k) => style.NODE_STYLE[k].shape);
  assert.equal(new Set(shapes).size, NODE_KINDS.length);
  for (const k of NODE_KINDS) assert.match(style.NODE_STYLE[k].tint, /^#[0-9a-f]{6}$/i);
});

test("edge kinds follow the UML-style spec", () => {
  const e = style.EDGE_STYLE;
  assert.deepEqual([e.calls.line, e.calls.arrow, e.calls.fill], ["solid", "triangle", "filled"]);
  assert.deepEqual([e.inherits.arrow, e.inherits.fill], ["triangle", "hollow"]);
  assert.equal(e.imports.line, "dashed");
  assert.equal(e.references.line, "dotted");
  assert.equal(e.instantiates.arrow, "diamond");
  for (const k of EDGE_KINDS) assert.match(e[k].hue, /^#[0-9a-f]{6}$/i);
  assert.ok(e.references.width < e.calls.width, "references are thin");
});

test("stylesheet has a rule per node kind and edge kind, external dashed, filtered hidden", () => {
  const rules = style.buildStylesheet();
  const sel = rules.map((r) => r.selector);
  for (const k of NODE_KINDS) assert.ok(sel.includes(`node[kind = "${k}"]`), k);
  for (const k of EDGE_KINDS) assert.ok(sel.includes(`edge[kind = "${k}"]`), k);
  assert.equal(rules.find((r) => r.selector === "node[?external]").style["border-style"], "dashed");
  assert.equal(rules.find((r) => r.selector === ".filtered").style.display, "none");
});

test("extension points: extra rule sets are appended last", () => {
  const extra = { selector: "node[?stub]", style: { "border-style": "double" } };
  const rules = style.buildStylesheet([extra]);
  assert.equal(rules[rules.length - 1], extra);
  assert.deepEqual(style.buildStylesheet([() => [extra]]).at(-1), extra, "functions are called with the tokens");
});

test("language badge is a data URI per language with a fallback", () => {
  assert.match(style.languageBadge("cpp"), /^data:image\/svg\+xml/);
  assert.notEqual(style.languageBadge("cpp"), style.languageBadge("ada"));
  assert.match(style.languageBadge("zig"), /^data:image\/svg\+xml/);
  assert.equal(style.languageBadge(null), "none");
});

test("labels are constant on-screen size: font scales inversely with zoom", () => {
  const a = style.labelMetrics(0.5), b = style.labelMetrics(2);
  assert.ok(Math.abs(a.fontSize * 0.5 - b.fontSize * 2) < 1e-9);
});

test("below the zoom threshold only the focus and hovered neighbors are labelled", () => {
  const z = style.LABEL_ZOOM_THRESHOLD - 0.05;
  assert.equal(style.labelText("area", { zoom: z }), "");
  assert.equal(style.labelText("area", { zoom: z, isFocus: true }), "area");
  assert.equal(style.labelText("area", { zoom: z, emphasised: true }), "area");
  assert.equal(style.labelText("area", { zoom: style.LABEL_ZOOM_THRESHOLD }), "area");
});

test("long labels get an ellipsis", () => {
  const out = style.labelText("x".repeat(60), { zoom: 1 });
  assert.ok(out.length <= style.MAX_LABEL_CHARS && out.endsWith("…"));
});

test("filters: toggling node kinds is immutable and visibility follows it", () => {
  const f0 = filters.defaultFilters();
  assert.equal(filters.isNodeKindVisible(f0, "function"), true);
  const f1 = filters.toggleNodeKind(f0, "function");
  assert.equal(filters.isNodeKindVisible(f1, "function"), false);
  assert.equal(filters.isNodeKindVisible(f0, "function"), true);
  assert.equal(filters.isNodeKindVisible(filters.toggleNodeKind(f1, "function"), "function"), true);
});

test("filters: a hidden endpoint hides its edges; focus is never hidden", () => {
  const f = filters.toggleNodeKind(filters.defaultFilters(), "class");
  assert.equal(filters.isNodeVisible(f, { kind: "class", isFocus: true }), true);
  assert.equal(filters.isNodeVisible(f, { kind: "class" }), false);
  assert.equal(filters.isEdgeVisible(f, { kind: "calls" }, { kind: "class" }, { kind: "function" }), false);
  assert.equal(filters.isEdgeVisible(f, { kind: "calls" }, { kind: "function" }, { kind: "function" }), true);
  const g = filters.toggleEdgeKind(filters.defaultFilters(), "imports");
  assert.equal(filters.isEdgeVisible(g, { kind: "imports" }, { kind: "file" }, { kind: "file" }), false);
});

test("filters: edge kinds map to the API kinds param only when something is hidden", () => {
  const f0 = filters.defaultFilters();
  assert.equal(filters.edgeKindsParam(f0), undefined);
  const f1 = filters.toggleEdgeKind(f0, "contains");
  assert.deepEqual(filters.edgeKindsParam(f1), EDGE_KINDS.filter((k) => k !== "contains"));
});

test("filters round-trip through URL-friendly params", () => {
  let f = filters.toggleNodeKind(filters.defaultFilters(), "type");
  f = filters.toggleEdgeKind(f, "imports");
  assert.deepEqual(filters.filtersToParams(f), { hideNodes: "type", hideEdges: "imports" });
  assert.deepEqual(filters.filtersFromParams(filters.filtersToParams(f)), f);
  assert.deepEqual(filters.filtersToParams(filters.defaultFilters()), {});
  assert.deepEqual(filters.filtersFromParams({}), filters.defaultFilters());
});

test("legend model lists all known kinds with counts and checked state", () => {
  const f = filters.toggleNodeKind(filters.defaultFilters(), "method");
  const m = legend.legendModel(f, { nodes: { function: 3, method: 2, weird: 1 }, edges: { calls: 4 } });
  const fn = m.nodes.find((r) => r.kind === "function");
  assert.deepEqual([fn.checked, fn.count], [true, 3]);
  assert.equal(m.nodes.find((r) => r.kind === "method").checked, false);
  assert.ok(m.nodes.find((r) => r.kind === "weird"), "unknown kinds present in the data are listed");
  assert.equal(m.edges.length, EDGE_KINDS.length);
  assert.equal(m.edges.find((r) => r.kind === "calls").count, 4);
});

test("mini legend shows only visible kinds present in the view", () => {
  const f = filters.toggleNodeKind(filters.defaultFilters(), "method");
  const mini = legend.miniLegendModel(f, { nodes: { function: 3, method: 2 }, edges: { calls: 4, imports: 0 } });
  assert.deepEqual(mini.nodes.map((r) => r.kind), ["function"]);
  assert.deepEqual(mini.edges.map((r) => r.kind), ["calls"]);
});

test("every node shape has a legend swatch drawing", () => {
  for (const k of NODE_KINDS) assert.ok(legend.shapePoints(style.NODE_STYLE[k].shape), k);
});

test("elements carry the badge the style reads", () => {
  const { nodes } = toElements({
    focus: "a", edges: [],
    nodes: [{ id: "a", name: "a", kind: "function", language: "cpp", external: false, depth: 0 }],
  });
  assert.equal(nodes[0].data.badge, style.languageBadge("cpp"));
});

test("countKinds tallies a neighborhood response", () => {
  const c = legend.countKinds({ nodes: [{ kind: "class" }, { kind: "class" }, { kind: "type" }], edges: [{ kind: "calls" }] });
  assert.deepEqual(c, { nodes: { class: 2, type: 1 }, edges: { calls: 1 } });
});
