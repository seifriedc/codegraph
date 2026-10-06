// Hierarchy view unit tests (pure modules + the real vendored dagre). Run: node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const staticDir = path.join(here, "..", "..", "codegraph", "vis", "static");
const load = (f) => import(path.join(staticDir, f));

const { parseHash, formatHash, DEFAULTS } = await load("state.js");
const { fetchHierarchy } = await load("api.js");
const { layeredPositions, HIERARCHY_MODES } = await load("hierarchy_layout.js");

function loadDagre() {
  const ctx = vm.createContext({ console, structuredClone });
  vm.runInContext(fs.readFileSync(path.join(staticDir, "vendor", "dagre.min.js"), "utf8") + "\n;this.dagre = dagre;", ctx);
  return ctx.dagre;
}

test("state carries the view key (separate from the reach mode) and omits the default", () => {
  assert.equal(parseHash("#focus=Shape&view=type").view, "type");
  assert.equal(parseHash("#focus=Shape&view=declaration").view, "declaration");
  assert.equal(parseHash("#focus=Shape&view=bogus").view, DEFAULTS.view);
  assert.equal(parseHash("#focus=Shape&mode=impact&view=type").mode, "impact");
  assert.equal(formatHash({ ...DEFAULTS, focus: "x", view: "type" }), "#focus=x&view=type");
  assert.equal(formatHash({ ...DEFAULTS, focus: "x" }), "#focus=x");
});

test("fetchHierarchy builds the query and maps 404 to null", async () => {
  let seen;
  const f = async (u) => { seen = u; return { status: 404 }; };
  assert.equal(await fetchHierarchy("a b", { mode: "type", limit: 50 }, f), null);
  assert.equal(seen, "/api/hierarchy/a%20b?mode=type&limit=50");
});

const SHAPE_NODES = ["Shape", "Circle", "Rectangle"].map((id) => ({ id, w: 80, h: 30 }));
const SHAPE_EDGES = [{ source: "Circle", target: "Shape" }, { source: "Rectangle", target: "Shape" }];

test("type mode lays parents above children even though inherits edges point child -> parent", () => {
  const pos = layeredPositions(loadDagre(), SHAPE_NODES, SHAPE_EDGES, "type");
  assert.ok(pos.Shape.y < pos.Circle.y);
  assert.equal(pos.Circle.y, pos.Rectangle.y);
  assert.notEqual(pos.Circle.x, pos.Rectangle.x);
});

test("declaration mode lays containers above members (edges already point down)", () => {
  const nodes = ["C", "C::a", "C::b"].map((id) => ({ id, w: 80, h: 30 }));
  const edges = [{ source: "C", target: "C::a" }, { source: "C", target: "C::b" }];
  const pos = layeredPositions(loadDagre(), nodes, edges, "declaration");
  assert.ok(pos.C.y < pos["C::a"].y);
});

test("unknown modes are rejected and dangling edges ignored", () => {
  assert.deepEqual(HIERARCHY_MODES, ["type", "declaration"]);
  const pos = layeredPositions(loadDagre(), SHAPE_NODES, [...SHAPE_EDGES, { source: "Circle", target: "ghost" }], "type");
  assert.equal(Object.keys(pos).length, 3);
});
