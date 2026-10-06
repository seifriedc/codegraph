// The Cytoscape canvas: shows neighborhood responses, keeps positions stable across refocus,
// owns the live layout. `cytoscape` and `d3` are injected (vendored UMD globals; see index.html).
import { toElements } from "./elements.js";
import { createForceLayout } from "./layout.js";
import { layeredPositions } from "./hierarchy_layout.js";
import { buildStylesheet } from "./style.js";
import { defaultFilters, isEdgeVisible, isNodeVisible } from "./filters.js";

export function createCanvas(container, { cytoscape, d3, dagre, onTapNode = () => {}, onLayoutState = () => {}, styleRules = [], cyOptions = {} }) {
  const cy = cytoscape({
    container, style: buildStylesheet(styleRules), wheelSensitivity: 0.3, minZoom: 0.1, maxZoom: 3, ...cyOptions,
  });
  let autoFit = true;
  let filters = defaultFilters();

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

  // Labels are constant on-screen size: re-evaluate the zoom-dependent style functions when zoom changes.
  let zoomPending = false;
  cy.on("zoom", () => {
    if (zoomPending) return;
    zoomPending = true;
    requestAnimationFrame(() => { zoomPending = false; cy.nodes().updateStyle(); });
  });

  // Hover emphasises a node and its neighbours (their labels show even when zoomed out).
  cy.on("mouseover", "node", (evt) => evt.target.closedNeighborhood().addClass("emphasised"));
  cy.on("mouseout", "node", () => cy.elements().removeClass("emphasised"));

  /** Apply legend filters as visibility (class `filtered`); the data stays in the graph. */
  function setFilters(next) {
    filters = next;
    cy.batch(() => {
      cy.nodes().forEach((n) => n.toggleClass("filtered", !isNodeVisible(filters, n.data())));
      cy.edges().forEach((e) => e.toggleClass("filtered",
        !isEdgeVisible(filters, e.data(), e.source().data(), e.target().data())));
    });
  }

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

    setFilters(filters);
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
    setFilters(filters);
    autoFit = true;
    recenter(false);
    onLayoutState("sleeping");
  }

  function destroy() { layout.stop(); cy.destroy(); }

  return { cy, show, showHierarchy, recenter, setFilters, destroy, layout };
}
