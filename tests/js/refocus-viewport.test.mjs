// Refocus (click a node) must move the viewport smoothly once, never snap when the layout settles.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const staticDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "codegraph", "vis", "static");
const { createCanvas } = await import(path.join(staticDir, "canvas.js"));

// Manual frame clock: time only advances when the test says so.
let clock = 0, frames = [];
globalThis.requestAnimationFrame = (f) => frames.push(f) && frames.length;
globalThis.cancelAnimationFrame = () => {};
const ctx = vm.createContext({ console, setTimeout, clearTimeout, setInterval, clearInterval, performance: { now: () => clock } });
vm.runInThisContext(fs.readFileSync(path.join(staticDir, "vendor", "cytoscape.min.js"), "utf8"));
for (const f of ["d3-dispatch", "d3-quadtree", "d3-timer", "d3-force"]) {
  vm.runInContext(fs.readFileSync(path.join(staticDir, "vendor", f + ".min.js"), "utf8"), ctx);
}

const node = (id, depth = 1) => ({ id, kind: "function", name: id, qualified_name: id, depth, external: false, language: "cpp" });
const hood = (focus, ids) => ({
  focus, nodes: ids.map((i) => node(i, i === focus ? 0 : 1)),
  edges: ids.filter((i) => i !== focus).map((i) => ({ id: `e-${focus}-${i}`, kind: "calls", source_id: i, target_id: focus })),
  stubs: [], truncated: false, total: ids.length,
});

/** Run frames for `ms` of fake time at 60fps, sampling the viewport each frame. */
function run(cy, ms, samples) {
  for (let t = 0; t < ms; t += 16) {
    clock += 16;
    cy.__tick?.(clock);
    const batch = frames; frames = [];
    batch.forEach((f) => f());
    samples.push({ t: clock, zoom: cy.zoom(), pan: { ...cy.pan() } });
  }
}

test("refocus on a clicked node never snaps the viewport when the layout settles", async () => {
  const handlers = {};
  const container = { addEventListener: (type, h) => (handlers[type] = h) };
  const canvas = createCanvas(container, { cytoscape: globalThis.cytoscape, d3: ctx.d3, cyOptions: { headless: true, container: undefined } });
  const cy = canvas.cy;
  cy.width = () => 800; cy.height = () => 600;
  // Cytoscape does not run animations headless: record them and apply their end state.
  const animations = [];
  cy.animate = (props, opts) => { animations.push({ props, opts }); if (props.center) cy.center(props.center.eles); return cy; };
  canvas.show(hood("f", ["f", "a", "b", "c", "d", "e"]));
  const warm = []; run(cy, 5000, warm);          // initial layout settles + fits
  // user pans/zooms a bit, then clicks node "a" (pointerdown precedes tap)
  cy.zoom({ level: 1.5, renderedPosition: { x: 400, y: 300 } });
  handlers.pointerdown();
  const before = { zoom: cy.zoom(), pan: { ...cy.pan() } };
  canvas.show(hood("a", ["a", "f", "x", "y", "z"]));  // what main.js does on hashchange
  const samples = []; run(cy, 6000, samples);
  // biggest single-frame jump in the rendered position of the new focus node
  let maxJump = 0, prev = null;
  for (const s of samples) {
    const p = cy.getElementById("a").position();
    const r = { x: p.x * s.zoom + s.pan.x, y: p.y * s.zoom + s.pan.y };
    if (prev) maxJump = Math.max(maxJump, Math.hypot(r.x - prev.x, r.y - prev.y));
    prev = r;
  }
  const last = samples.at(-1);
  const p = cy.getElementById("a").position();
  assert.ok(Math.abs(p.x * last.zoom + last.pan.x - 400) < 2 && Math.abs(p.y * last.zoom + last.pan.y - 300) < 2, "focus ends centred");
  assert.ok(animations.some((a) => a.props.center && a.opts.duration > 0), "the move to the new focus is animated");
  assert.equal(last.zoom, before.zoom, "zoom is left alone");
  assert.ok(maxJump < 40, `viewport jumped ${maxJump.toFixed(1)}px in one frame`);
});

test("the first render's settle-time fit is animated, never a snap", () => {
  const container = { addEventListener() {} };
  const canvas = createCanvas(container, { cytoscape: globalThis.cytoscape, d3: ctx.d3, cyOptions: { headless: true, container: undefined } });
  const cy = canvas.cy;
  cy.width = () => 800; cy.height = () => 600;
  const animations = [];
  cy.animate = (props, opts) => { animations.push({ props, opts }); return cy; }; // not applied: any viewport change is a snap
  canvas.show(hood("f", ["f", "a", "b", "c", "d", "e"]));
  const start = { zoom: cy.zoom(), pan: { ...cy.pan() } };
  run(cy, 5000, []);
  assert.deepEqual({ zoom: cy.zoom(), pan: { ...cy.pan() } }, start, "viewport untouched by settling");
  assert.ok(animations.some((a) => a.props.fit && a.opts.duration > 0), "settle fit is animated");
});
