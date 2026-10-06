// Optional unit tests for the pure UI modules. Run outside pytest:  node --test tests/js
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
const { shortLabel, toElements, statusText } = await load("elements.js");
const { neighbourRows } = await load("panel.js");
const { createForceLayout, SETTLE } = await load("layout.js");
const { fetchNeighborhood } = await load("api.js");

test("state round-trips and omits defaults", () => {
  const s = { ...DEFAULTS, focus: "Shape", view: "focus", depth: 3, direction: "in" };
  assert.deepEqual(parseHash(formatHash(s)), s);
  assert.equal(formatHash({ ...DEFAULTS, focus: "x", view: "focus" }), "#focus=x");
  assert.equal(formatHash({ ...DEFAULTS, focus: null }), "");
});

test("state falls back to defaults on junk", () => {
  assert.deepEqual(parseHash("#depth=99&direction=up"), { ...DEFAULTS, focus: null });
});

test("short labels", () => {
  assert.equal(shortLabel({ kind: "method", qualified_name: "Circle::area", name: "area" }), "area");
  assert.equal(shortLabel({ kind: "file", qualified_name: "cpp/shapes.cpp", name: "shapes.cpp" }), "shapes.cpp");
  assert.equal(shortLabel({ kind: "package", qualified_name: "Geometry.Utils", name: "Utils" }), "Utils");
});

test("toElements drops dangling edges and marks the focus", () => {
  const resp = {
    focus: "a",
    nodes: [{ id: "a", kind: "class", name: "A", qualified_name: "A", depth: 0, external: false, language: "cpp" },
            { id: "b", kind: "class", name: "B", qualified_name: "B", depth: 1, external: false, language: "cpp" }],
    edges: [{ id: "1", kind: "inherits", source_id: "b", target_id: "a" },
            { id: "2", kind: "calls", source_id: "b", target_id: "zzz" }],
  };
  const { nodes, edges } = toElements(resp);
  assert.deepEqual(nodes.map((n) => n.data.isFocus), [true, false]);
  assert.deepEqual(edges.map((e) => e.data.id), ["1"]);
});

test("statusText reports truncation", () => {
  assert.match(statusText({ nodes: new Array(150), total: 1204, truncated: true }), /150 of 1,204/);
  assert.equal(statusText({ nodes: [1], total: 1, truncated: false }), "Showing 1 node");
});

test("neighbourRows zero-fills and sorts", () => {
  assert.deepEqual(neighbourRows({ in: { inherits: 2 }, out: { contains: 2 } }),
    [{ kind: "contains", in: 0, out: 2 }, { kind: "inherits", in: 2, out: 0 }]);
});

test("fetchNeighborhood builds the query and maps 404 to null", async () => {
  let seen;
  const f = async (u) => { seen = u; return { status: 404 }; };
  assert.equal(await fetchNeighborhood("a b", { depth: 2, direction: "in", kinds: ["calls", "inherits"] }, f), null);
  assert.equal(seen, "/api/neighborhood/a%20b?depth=2&direction=in&kinds=calls%2Cinherits");
});

// ---- layout lifecycle with the real vendored d3-force and a fake Cytoscape ----

function loadD3() {
  const ctx = vm.createContext({ console, setTimeout, clearTimeout, setInterval, clearInterval, performance });
  for (const f of ["d3-dispatch", "d3-quadtree", "d3-timer", "d3-force"]) {
    vm.runInContext(fs.readFileSync(path.join(staticDir, "vendor", f + ".min.js"), "utf8"), ctx);
  }
  return ctx.d3;
}

function fakeCy(ids, links) {
  const pos = Object.fromEntries(ids.map((id, i) => [id, { x: 40 * i, y: (i % 3) * 30 }]));
  const handlers = {};
  const ele = (id) => ({
    id: () => id, nonempty: () => id in pos, grabbed: () => false,
    position: (a, b) => (typeof a === "object" ? (pos[id] = { ...a }) : pos[id][a]),
    data: (k) => (k === "source" ? links[id][0] : links[id][1]),
  });
  return {
    pos, handlers,
    nodes: () => ids.map(ele),
    edges: () => Object.keys(links).map(ele),
    getElementById: ele,
    batch: (f) => f(),
    on: (ev, sel, h) => { handlers[ev] = h; },
    off: (ev) => { delete handlers[ev]; },
  };
}

function harness(extra = {}) {
  const d3 = loadD3();
  const ids = ["f", "a", "b", "c", "d"];
  const cy = fakeCy(ids, { e1: ["f", "a"], e2: ["f", "b"], e3: ["a", "c"], e4: ["b", "d"] });
  let queue = [], clock = 0;
  const events = [];
  const layout = createForceLayout(cy, d3, {
    raf: (f) => queue.push(f), caf: () => { queue = []; }, now: () => clock,
    onSleep: () => events.push("sleep"), onWake: () => events.push("wake"), ...extra,
  });
  const run = (maxFrames = 2000) => {
    let n = 0;
    while (queue.length && n++ < maxFrames) { const f = queue.shift(); f(); }
    return n;
  };
  return { cy, layout, run, events, advance: (ms) => { clock += ms; } };
}

test("layout settles and sleeps within the hard tick bound", () => {
  const h = harness();
  h.cy.pos.f = { x: 0, y: 0 };
  h.layout.start("f");
  const frames = h.run();
  assert.ok(frames <= SETTLE.maxTicks, `ticked ${frames} frames`);
  assert.equal(h.layout.isSleeping(), true);
  assert.deepEqual(h.events, ["wake", "sleep"]);
  assert.equal(h.run(), 0, "no frames scheduled while asleep");
});

test("the focus node stays pinned while others move", () => {
  const h = harness();
  h.cy.pos.f = { x: 10, y: 20 };
  const before = { a: { ...h.cy.pos.a } };
  h.layout.start("f");
  h.run();
  assert.deepEqual(h.cy.pos.f, { x: 10, y: 20 });
  assert.notDeepEqual(h.cy.pos.a, before.a);
});

test("dragging another node wakes the sim, never moves the focus, and it sleeps again", () => {
  const h = harness();
  h.layout.start("f");
  h.run();
  const focusPos = { ...h.cy.pos.f };
  const target = (id) => ({ target: h.cy.getElementById(id) });
  h.cy.handlers.grab(target("a"));
  assert.equal(h.layout.isSleeping(), false);
  h.cy.pos.a = { x: 300, y: 300 };
  h.cy.handlers.drag(target("a"));
  h.run(50); // keeps ticking while held (alphaTarget > 0): never sleeps mid-drag
  assert.equal(h.layout.isSleeping(), false);
  h.cy.handlers.free(target("a"));
  h.run();
  assert.equal(h.layout.isSleeping(), true);
  assert.deepEqual(h.cy.pos.f, focusPos);
});

test("wall-clock bound also stops the simulation", () => {
  const h = harness({ config: { alphaDecay: 0.0001 } }); // would never cool by alpha alone
  h.layout.start("f");
  let n = 0;
  while (!h.layout.isSleeping() && n++ < 10000) { h.advance(100); h.run(1); }
  assert.equal(h.layout.isSleeping(), true);
});
