// Canvas behaviour for the scale policy against the real vendored Cytoscape (headless) and d3-force.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const staticDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "codegraph", "vis", "static");
const { createCanvas } = await import(path.join(staticDir, "canvas.js"));
const { createModel } = await import(path.join(staticDir, "scale.js"));

// The layout's frame loop is not under test here: frames are scheduled but never run.
globalThis.requestAnimationFrame = () => 0;
globalThis.cancelAnimationFrame = () => {};

const ctx = vm.createContext({ console, setTimeout, clearTimeout, setInterval, clearInterval, performance });
// Cytoscape checks plain-object-ness, so it must share our realm; d3 can live in its own context.
vm.runInThisContext(fs.readFileSync(path.join(staticDir, "vendor", "cytoscape.min.js"), "utf8"));
for (const f of ["d3-dispatch", "d3-quadtree", "d3-timer", "d3-force"]) {
  vm.runInContext(fs.readFileSync(path.join(staticDir, "vendor", f + ".min.js"), "utf8"), ctx);
}

const node = (id, depth = 1) => ({ id, kind: "function", name: id, qualified_name: id, depth, external: false, language: "cpp" });
const base = {
  focus: "f", nodes: [node("f", 0), node("a")],
  edges: [{ id: "e1", kind: "calls", source_id: "a", target_id: "f" }],
  stubs: [{ id: "stub:f:in:calls", owner: "f", direction: "in", kind: "calls", hidden: 3, offset: 1 }],
  truncated: false, total: 2,
};

function setup() {
  const taps = { node: [], stub: [] };
  const container = { addEventListener() {} };
  const canvas = createCanvas(container, {
    cytoscape: globalThis.cytoscape, d3: ctx.d3, cyOptions: { headless: true, container: undefined },
    onTapNode: (id) => taps.node.push(id), onTapStub: (s) => taps.stub.push(s),
  });
  return { canvas, taps, cy: canvas.cy };
}

test("stubs render as flagged nodes joined to their owner; tapping one reports the stub, not a refocus", () => {
  const { canvas, taps, cy } = setup();
  const m = createModel();
  m.reset(base);
  canvas.show(m.view());
  const stub = cy.getElementById("stub:f:in:calls");
  assert.equal(stub.data("isStub"), true);
  assert.equal(stub.data("label"), "+3 calls in");
  assert.equal(cy.getElementById("edge:stub:f:in:calls").data("source"), "f");
  stub.emit("tap");
  assert.equal(taps.stub[0].owner, "f");
  assert.deepEqual(taps.node, []);
  cy.getElementById("a").emit("tap");
  assert.deepEqual(taps.node, ["a"]);
  canvas.destroy();
});

test("an expansion keeps existing positions, spawns near the owner, highlights new nodes and undo removes them", () => {
  const { canvas, cy } = setup();
  const m = createModel();
  m.reset(base);
  canvas.show(m.view());
  cy.getElementById("a").position({ x: 500, y: 500 });
  const before = { ...cy.getElementById("a").position() };
  const r = m.expand("stub:f:in:calls", {
    owner: "f", nodes: [node("c"), node("d")], total: 3,
    edges: [{ id: "x1", kind: "calls", source_id: "c", target_id: "f" }],
    stub: { id: "stub:f:in:calls", owner: "f", direction: "in", kind: "calls", hidden: 1, offset: 3 },
  });
  canvas.show(m.view(), { anchor: "f", highlight: r.added, expansion: true });
  assert.deepEqual(cy.getElementById("a").position(), before);
  assert.equal(cy.getElementById("c").hasClass("fresh"), true);
  assert.equal(cy.getElementById("a").hasClass("fresh"), false);
  assert.equal(cy.getElementById("stub:f:in:calls").data("hidden"), 1);
  m.undo();
  canvas.show(m.view(), { expansion: true });
  assert.equal(cy.getElementById("c").empty(), true);
  assert.equal(cy.getElementById("stub:f:in:calls").data("hidden"), 3);
  canvas.highlight([]);
  canvas.destroy();
});
