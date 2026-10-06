// The Cytoscape canvas: shows neighborhood responses, keeps positions stable across refocus,
// owns the live layout. `cytoscape` and `d3` are injected (vendored UMD globals; see index.html).
import { toElements } from "./elements.js";
import { createForceLayout } from "./layout.js";
import { layeredPositions } from "./hierarchy_layout.js";
import { stylesheet } from "./style.js";

export function createCanvas(container, { cytoscape, d3, dagre, onTapNode = () => {}, onLayoutState = () => {}, cyOptions = {} }) {
  const cy = cytoscape({
    container, style: stylesheet, wheelSensitivity: 0.3, minZoom: 0.1, maxZoom: 3, ...cyOptions,
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

  cy.on("tap", "node", (evt) => onTapNode(evt.target.id()));

  /** Fit all elements in view. Also the "recenter" button's action. */
  function recenter(animate = true) {
    cy.resize();
    if (cy.elements().empty()) return;
    const opts = { eles: cy.elements(), padding: 40 };
    if (animate) cy.animate({ fit: opts }, { duration: 250 });
    else cy.fit(opts.eles, opts.padding);
  }

  /** Replace the displayed graph with `resp`, keeping nodes that stay (and their positions). */
  function show(resp) {
    const { nodes, edges } = toElements(resp);
    const keep = new Set([...nodes, ...edges].map((e) => e.data.id));
    const hadNodes = cy.nodes().nonempty();

    cy.batch(() => {
      cy.elements().filter((e) => !keep.has(e.id())).remove();
      const fresh = [];
      let i = 0;
      for (const n of nodes) {
        const existing = cy.getElementById(n.data.id);
        if (existing.nonempty()) {
          existing.data(n.data);
        } else {
          // spawn new nodes on a small ring around the origin/focus so the sim starts untangled
          const a = (i++ / Math.max(1, nodes.length)) * 2 * Math.PI;
          const r = n.data.isFocus ? 0 : 60 + 25 * (n.data.depth || 1);
          fresh.push({ ...n, position: { x: r * Math.cos(a), y: r * Math.sin(a) } });
        }
      }
      for (const e of edges) if (cy.getElementById(e.data.id).empty()) fresh.push(e);
      cy.add(fresh);
    });

    autoFit = true;
    if (!hadNodes) recenter(false);
    layout.start(resp.focus);
  }

  /** Replace the displayed graph with a hierarchy response, laid out top to bottom with dagre. */
  function showHierarchy(resp, mode) {
    layout.stop();
    const { nodes, edges } = toElements(resp);
    const sized = nodes.map((n) => ({ id: n.data.id, w: Math.max(60, n.data.label.length * 7 + 20), h: 34 }));
    const positions = layeredPositions(dagre, sized, edges.map((e) => ({ source: e.data.source, target: e.data.target })), mode);
    cy.batch(() => {
      cy.elements().remove();
      cy.add([...nodes.map((n) => ({ ...n, position: positions[n.data.id] })), ...edges]);
    });
    autoFit = true;
    recenter(false);
    onLayoutState("sleeping");
  }

  function destroy() { layout.stop(); cy.destroy(); }

  return { cy, show, showHierarchy, recenter, destroy, layout };
}
