// Additive Cytoscape rules for the scale policy: Stub nodes and the new-node highlight.
// Deliberately separate from style.js (owned by the visual-encoding ticket, which will fold these in).

export const FRESH_CLASS = "fresh";

export const scaleStylesheet = [
  {
    selector: "node[?isStub]",
    style: {
      shape: "round-rectangle", width: "label", height: 20, padding: "4px", "background-color": "#fff", "background-opacity": 1,
      "border-width": 1.5, "border-style": "dashed", "border-color": "#1d4ed8", color: "#1d4ed8",
      label: "data(label)", "font-size": 10, "text-valign": "center", "text-halign": "center",
      "text-margin-y": 0, "text-max-width": 80, "text-wrap": "none", "min-zoomed-font-size": 0,
    },
  },
  { selector: "edge[?isStubEdge]", style: { "line-style": "dashed", "line-color": "#1d4ed8", "target-arrow-shape": "none", opacity: 0.6 } },
  {
    selector: `node.${FRESH_CLASS}`,
    style: { "border-color": "#ea580c", "border-width": 3.5, "underlay-color": "#fb923c", "underlay-opacity": 0.35, "underlay-padding": 6 },
  },
];
