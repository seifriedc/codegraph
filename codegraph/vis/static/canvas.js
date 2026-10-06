// The Cytoscape canvas: shows neighborhood responses, keeps positions stable across refocus,
// owns the live layout. `cytoscape` and `d3` are injected (vendored UMD globals; see index.html).
import { toElements } from "./elements.js";
import { createForceLayout } from "./layout.js";
import { stylesheet } from "./style.js";
import { FRESH_CLASS, scaleStylesheet } from "./scale-style.js";
import { stubElements } from "./scale.js";

export function createCanvas(container, { cytoscape, d3, onTapNode = () => {}, onTapStub = () => {}, onLayoutState = () => {}, cyOptions = {} }) {
  const cy = cytoscape({
    container, style: [...stylesheet, ...scaleStylesheet], wheelSensitivity: 0.3, minZoom: 0.1, maxZoom: 3, ...cyOptions,
  });
  let autoFit = true;

  const layout = createForceLayout(cy, d3, {
    onWake: () => onLayoutState("running"),
    onSleep: () => {
      if (autoFit) recenter(false);
      onLayoutState("sleeping");
    },
  });

  // Once the user pans or zooms themselves, stop re-fitting when the layout settles.
  for (const type of ["wheel", "pointerdown"]) {
    container.addEventListener(type, () => { autoFit = false; }, { passive: true });
  }

  cy.on("tap", "node", (evt) => {
    if (evt.target.data("isStub")) onTapStub(evt.target.data());
    else onTapNode(evt.target.id());
  });

  /** Fit all elements in view. Also the "recenter" button's action. */
  function recenter(animate = true) {
    cy.resize();
    if (cy.elements().empty()) return;
    const opts = { eles: cy.elements(), padding: 40 };
    if (animate) cy.animate({ fit: opts }, { duration: 250 });
    else cy.fit(opts.eles, opts.padding);
  }

  let freshTimer = null;

  /** Highlight `ids` as newly added (cleared after a few seconds or on the next show). */
  function highlight(ids, ms = 4000) {
    clearTimeout(freshTimer);
    cy.nodes().removeClass(FRESH_CLASS);
    for (const id of ids) cy.getElementById(id).addClass(FRESH_CLASS);
    if (ids.length) freshTimer = setTimeout(() => cy.nodes().removeClass(FRESH_CLASS), ms);
  }

  /**
   * Replace the displayed graph with `resp` (nodes, edges and optional Stub nodes), keeping nodes
   * that stay (and their positions). Options: `anchor` (node id) spawns new nodes around that node
   * instead of the origin; `highlight` (ids) marks them as new; `expansion` keeps the current view.
   */
  function show(resp, { anchor = null, highlight: fresh = [], expansion = false } = {}) {
    const base = toElements(resp);
    const sx = stubElements(resp.stubs || [], new Set(base.nodes.map((n) => n.data.id)));
    const nodes = [...base.nodes, ...sx.nodes];
    const edges = [...base.edges, ...sx.edges];
    const anchorEle = anchor ? cy.getElementById(anchor) : null;
    const center = anchorEle && anchorEle.nonempty() ? anchorEle.position() : { x: 0, y: 0 };
    const keep = new Set([...nodes, ...edges].map((e) => e.data.id));
    const hadNodes = cy.nodes().nonempty();

    cy.batch(() => {
      cy.elements().filter((e) => !keep.has(e.id())).remove();
      const add = [];
      let i = 0;
      for (const n of nodes) {
        const existing = cy.getElementById(n.data.id);
        if (existing.nonempty()) {
          existing.data(n.data);
        } else {
          // spawn new nodes on a small ring around the origin/focus so the sim starts untangled
          const a = (i++ / Math.max(1, nodes.length)) * 2 * Math.PI;
          const r = n.data.isFocus ? 0 : anchorEle ? 50 : 60 + 25 * (n.data.depth || 1);
          const own = n.data.isStub ? cy.getElementById(n.data.owner) : null;
          const c = own && own.nonempty() ? own.position() : center;
          add.push({ ...n, position: { x: c.x + r * Math.cos(a), y: c.y + r * Math.sin(a) } });
        }
      }
      for (const e of edges) if (cy.getElementById(e.data.id).empty()) add.push(e);
      cy.add(add);
    });

    if (!expansion) autoFit = true;
    highlight(fresh);
    if (!hadNodes) recenter(false);
    layout.start(resp.focus);
  }

  function destroy() { layout.stop(); cy.destroy(); }

  return { cy, show, highlight, recenter, destroy, layout };
}
