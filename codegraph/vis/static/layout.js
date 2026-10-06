// Live d3-force layout driving Cytoscape (ADR 0003). No DOM access: `d3` and the frame
// scheduler are injected so the lifecycle can be tested with node.
//
// Lifecycle: start() -> ticking -> sleeping (stops ticking, bounded by maxTicks/maxMs)
//            -> wake() on interaction (drag) -> ticking -> sleeping ...
// The Focus node is pinned (fx/fy); other nodes are draggable and never move it.

export const SETTLE = Object.freeze({
  alphaDecay: 0.05,      // ~135 ticks from alpha 1 to alphaMin 0.001 (about 2 s at 60 fps)
  velocityDecay: 0.4,
  linkDistance: 90,
  linkStrength: 0.6,
  charge: -260,
  chargeDistanceMax: 400,
  collide: 30,           // radius tuned for short labels under nodes
  wakeAlpha: 0.5,
  dragAlphaTarget: 0.2,
  maxTicks: 300,         // hard stop per run regardless of alpha
  maxMs: 4000,
});

export function createForceLayout(cy, d3, opts = {}) {
  const cfg = { ...SETTLE, ...(opts.config || {}) };
  const raf = opts.raf || ((f) => requestAnimationFrame(f));
  const caf = opts.caf || ((id) => cancelAnimationFrame(id));
  const now = opts.now || (() => performance.now());
  const onSleep = opts.onSleep || (() => {});
  const onWake = opts.onWake || (() => {});

  let sim = null, byId = new Map(), focusId = null;
  let frameId = null, ticks = 0, t0 = 0, dragging = false, sleeping = true;

  function isSleeping() { return sleeping; }

  function writePositions() {
    cy.batch(() => {
      for (const n of byId.values()) {
        const ele = cy.getElementById(n.id);
        if (ele.nonempty() && !ele.grabbed()) ele.position({ x: n.x, y: n.y });
      }
    });
  }

  function frame() {
    frameId = null;
    if (!sim) return;
    sim.tick();
    ticks += 1;
    writePositions();
    const settled = sim.alpha() < sim.alphaMin();
    const exhausted = ticks >= cfg.maxTicks || now() - t0 >= cfg.maxMs;
    if (!dragging && (settled || exhausted)) sleep();
    else frameId = raf(frame);
  }

  function sleep() {
    if (frameId != null) caf(frameId);
    frameId = null;
    if (sleeping) return;
    sleeping = true;
    onSleep();
  }

  function wake(alpha = cfg.wakeAlpha) {
    if (!sim) return;
    ticks = 0;
    t0 = now();
    sim.alpha(Math.max(sim.alpha(), alpha));
    if (sleeping) { sleeping = false; onWake(); }
    if (frameId == null) frameId = raf(frame);
  }

  // Interaction: dragging a node fixes it under the pointer and keeps the sim warm.
  function onGrab(evt) {
    const n = byId.get(evt.target.id());
    if (!n) return;
    dragging = true;
    n.fx = evt.target.position("x");
    n.fy = evt.target.position("y");
    sim.alphaTarget(cfg.dragAlphaTarget);
    wake(cfg.wakeAlpha);
  }
  function onDrag(evt) {
    const n = byId.get(evt.target.id());
    if (!n) return;
    n.fx = evt.target.position("x");
    n.fy = evt.target.position("y");
  }
  function onFree(evt) {
    const n = byId.get(evt.target.id());
    if (!n) return;
    dragging = false;
    sim.alphaTarget(0);
    // the Focus node stays pinned where it was dropped; everything else floats again
    if (n.id !== focusId) { n.fx = null; n.fy = null; }
    wake(cfg.wakeAlpha);
  }

  function detach() {
    cy.off("grab", "node", onGrab);
    cy.off("drag", "node", onDrag);
    cy.off("free", "node", onFree);
  }

  function stop() {
    if (frameId != null) caf(frameId);
    frameId = null;
    if (sim) sim.stop();
    sim = null;
    byId = new Map();
    dragging = false;
    sleeping = true;
    detach();
  }

  /** (Re)build the simulation from the nodes and edges currently in `cy`, pinning `focus`. */
  function start(focus) {
    stop();
    focusId = focus;
    const nodes = cy.nodes().map((e) => ({ id: e.id(), x: e.position("x"), y: e.position("y"), fx: null, fy: null }));
    byId = new Map(nodes.map((n) => [n.id, n]));
    const pin = byId.get(focus);
    if (pin) { pin.fx = pin.x; pin.fy = pin.y; }
    const links = cy.edges()
      .map((e) => ({ source: byId.get(e.data("source")), target: byId.get(e.data("target")) }))
      .filter((l) => l.source && l.target);
    const cx = pin ? pin.x : 0, cyy = pin ? pin.y : 0;
    sim = d3.forceSimulation(nodes)
      .alphaDecay(cfg.alphaDecay)
      .velocityDecay(cfg.velocityDecay)
      .force("link", d3.forceLink(links).distance(cfg.linkDistance).strength(cfg.linkStrength))
      .force("charge", d3.forceManyBody().strength(cfg.charge).distanceMax(cfg.chargeDistanceMax))
      .force("collide", d3.forceCollide(cfg.collide))
      .force("center", d3.forceCenter(cx, cyy).strength(0.03))
      .stop(); // we drive ticks ourselves so the lifecycle is bounded and testable
    cy.on("grab", "node", onGrab);
    cy.on("drag", "node", onDrag);
    cy.on("free", "node", onFree);
    sleeping = true;
    wake(1);
  }

  return { start, stop, wake, isSleeping, simNode: (id) => byId.get(id) };
}
