// Cytoscape stylesheet. Minimal on purpose: the visual-encoding ticket owns shape/tint/badge/edge styles
// and the legend, and replaces the encoding rules here. Pure data (no DOM).

export const TINT = {
  function: "#9ec1ff", method: "#c4d9ff", class: "#ffc48a", type: "#ffdcb8",
  package: "#8fd9ae", module: "#dddddd", file: "#e6e6e6", field: "#e8c5e8",
};

export const stylesheet = [
  {
    selector: "node",
    style: {
      label: "data(label)", "font-size": 11, "min-zoomed-font-size": 8,
      "text-valign": "bottom", "text-margin-y": 3, "text-max-width": 90, "text-wrap": "ellipsis",
      "background-color": (ele) => TINT[ele.data("kind")] || "#dddddd",
      "border-width": 1.5, "border-color": "#555",
      width: 20, height: 20,
    },
  },
  { selector: "node[?external]", style: { "border-style": "dashed" } },
  {
    selector: "node[?isFocus]",
    style: { "border-width": 4, "border-color": "#111", width: 28, height: 28, label: "data(full)", "z-index": 99 },
  },
  {
    selector: "edge",
    style: {
      width: 1.5, "line-color": "#999", "target-arrow-color": "#999",
      "target-arrow-shape": "triangle", "curve-style": "bezier", "arrow-scale": 0.9, opacity: 0.8,
    },
  },
];
