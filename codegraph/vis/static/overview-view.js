// The Overview on the shared Cytoscape instance: compound Groups laid out with fcose (ADR 0003).
// DOM-free apart from the Cytoscape instance passed in; `cy.layout({name: "fcose"})` needs the
// vendored fcose extension to be registered (main.js does `cytoscape.use(cytoscapeFcose)`).
import { toOverviewElements } from "./overview-elements.js";

/** Compound-node and Aggregate-edge rules, appended after the shared stylesheet (additive only). */
export const overviewStyle = [
  {
    selector: "node[?group]",
    style: {
      shape: "round-rectangle", "background-color": "#d9e2ef", "border-color": "#6b7a90", "border-width": 1.5,
      width: (ele) => 28 + 8 * Math.log2(1 + (ele.data("memberCount") || 0)),
      height: (ele) => 22 + 5 * Math.log2(1 + (ele.data("memberCount") || 0)),
      "font-size": 12, "text-valign": "center", "text-halign": "center", "text-margin-y": 0,
      "text-max-width": 140, "text-wrap": "ellipsis",
    },
  },
  { selector: "node[kind = 'file'][?group]", style: { "background-color": "#eeeeee" } },
  { selector: "node[kind = 'external'][?group]", style: { "background-color": "#f4f4f4", "border-style": "dashed" } },
  {
    selector: "node[?group]:parent",
    style: {
      "background-opacity": 0.14, "border-opacity": 0.8, padding: 16, "text-valign": "top", "text-halign": "center",
      "text-margin-y": -4, "font-weight": "bold",
    },
  },
  { selector: "node:selected", style: { "border-width": 4, "border-color": "#1d4ed8" } },
  {
    selector: "edge[?aggregate]",
    style: { width: "data(w)", "line-color": "#8a93a3", "target-arrow-color": "#8a93a3", opacity: 0.7, "arrow-scale": 0.8 },
  },
  { selector: "edge[?aggregate]:selected, edge[?aggregate].hover", style: { "line-color": "#1d4ed8", "target-arrow-color": "#1d4ed8", opacity: 1 } },
];

export const FCOSE = Object.freeze({
  name: "fcose", quality: "default", animate: true, animationDuration: 400, fit: true, padding: 40,
  nodeSeparation: 90, idealEdgeLength: 110, nodeRepulsion: 9000, packComponents: true, tile: true,
});

export function createOverviewView(cy, { onLayoutState = () => {}, tooltip = null, layoutOptions = {} } = {}) {
  let layout = null;
  let hadOverview = false;

  /** Replace what is displayed with `resp`; surviving nodes keep their positions. */
  function show(resp) {
    const { nodes, edges } = toOverviewElements(resp);
    const keep = new Set([...nodes, ...edges].map((e) => e.data.id));
    const oldPos = new Map(cy.nodes().map((n) => [n.id(), { ...n.position() }]));

    cy.batch(() => {
      cy.elements().filter((e) => !keep.has(e.id())).remove();
      const fresh = [];
      for (const n of nodes) {
        const existing = cy.getElementById(n.data.id);
        if (existing.nonempty()) {
          const { parent, ...rest } = n.data;
          existing.data(rest);
          if ((existing.parent().id() || undefined) !== parent) existing.move({ parent: parent || null });
        } else {
          // new nodes (children of a just-expanded Group) start next to where their parent was
          const origin = oldPos.get(n.data.parent) || { x: 0, y: 0 };
          fresh.push({ ...n, position: { x: origin.x + Math.random() * 40 - 20, y: origin.y + Math.random() * 40 - 20 } });
        }
      }
      // parents must exist before children when adding
      fresh.sort((a, b) => Number(!!a.data.parent) - Number(!!b.data.parent));
      cy.add(fresh);
      for (const e of edges) {
        const existing = cy.getElementById(e.data.id);
        if (existing.nonempty()) existing.data(e.data);
        else cy.add(e);
      }
    });

    if (layout) layout.stop();
    // first draw: fresh random start; later: refine from the current positions so the view stays stable
    layout = cy.layout({ ...FCOSE, ...layoutOptions, randomize: !hadOverview });
    layout.on("layoutstart", () => onLayoutState("running"));
    layout.on("layoutstop", () => onLayoutState("sleeping"));
    layout.run();
    hadOverview = true;
  }

  function hide() {
    if (layout) layout.stop();
    layout = null;
    hadOverview = false;
    if (tooltip) tooltip.hidden = true;
  }

  // per-kind tooltip on Aggregate edges
  cy.on("mouseover", "edge[?aggregate]", (evt) => {
    evt.target.addClass("hover");
    if (!tooltip) return;
    const e = evt.target;
    const label = (id) => cy.getElementById(id).data("full") || id;
    tooltip.textContent = `${label(e.data("source"))} -> ${label(e.data("target"))}\n${e.data("tip")}`;
    const p = evt.renderedPosition || { x: 0, y: 0 };
    tooltip.style.left = `${p.x + 12}px`;
    tooltip.style.top = `${p.y + 12}px`;
    tooltip.hidden = false;
  });
  cy.on("mouseout", "edge[?aggregate]", (evt) => {
    evt.target.removeClass("hover");
    if (tooltip) tooltip.hidden = true;
  });

  return { show, hide };
}
