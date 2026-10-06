// Visual encoding (ticket 23): kind -> shape + tint, language -> badge, edge kind -> UML-style line/arrow + hue,
// label policy, and the Cytoscape stylesheet built from them. Pure data and functions (no DOM, no Cytoscape import).
//
// Extension points for other views (Stub nodes, Overview groups, hierarchy emphasis, ...):
//   - buildStylesheet(extraRuleSets): each item is a rule object, an array of rules, or a function
//     (tokens) => rule | rule[]. Extra rules are appended last, so they override these.
//   - createCanvas(..., { styleRules: [...] }) passes extraRuleSets through.
//   - Rules should select on data/classes (node[?stub], node:parent, .filtered) rather than editing the base rules.
// Colours live in TOKENS so a dark theme can swap them later (light theme only for v1).

export const TOKENS = Object.freeze({
  text: "#222222", textBg: "#ffffff", border: "#555555", focusBorder: "#111111",
  edgeMuted: "#9ca3af", hover: "#1d4ed8",
});

/** Shape + fill tint per node kind; shapes are all distinct so the graph reads without colour. */
export const NODE_STYLE = Object.freeze({
  file:     { shape: "cut-rectangle",  tint: "#e6e6e6" },
  module:   { shape: "octagon",        tint: "#dddddd" },
  package:  { shape: "hexagon",        tint: "#8fd9ae" },
  function: { shape: "ellipse",        tint: "#9ec1ff" },
  method:   { shape: "round-diamond",  tint: "#c4d9ff" },
  class:    { shape: "rectangle",      tint: "#ffc48a" },
  type:     { shape: "round-tag",      tint: "#ffdcb8" },
  variable: { shape: "round-triangle", tint: "#e8c5e8" },
});
export const FALLBACK_NODE_STYLE = Object.freeze({ shape: "ellipse", tint: "#dddddd" });
export const NODE_KINDS = Object.freeze(Object.keys(NODE_STYLE));

/** Line style, arrowhead and hue per edge kind (UML-like). `at` is the end carrying the arrowhead. */
export const EDGE_STYLE = Object.freeze({
  imports:      { line: "dashed", width: 1.5, hue: "#0f766e", arrow: "vee",      fill: "filled", at: "target" },
  calls:        { line: "solid",  width: 1.5, hue: "#2563eb", arrow: "triangle", fill: "filled", at: "target" },
  defines:      { line: "solid",  width: 1,   hue: "#64748b", arrow: "circle",   fill: "filled", at: "target" },
  contains:     { line: "solid",  width: 1,   hue: "#cbd5e1", arrow: "diamond",  fill: "hollow", at: "source" },
  inherits:     { line: "solid",  width: 1.8, hue: "#c2410c", arrow: "triangle", fill: "hollow", at: "target" },
  references:   { line: "dotted", width: 1,   hue: "#9ca3af", arrow: "vee",      fill: "filled", at: "target" },
  instantiates: { line: "solid",  width: 1.5, hue: "#7c3aed", arrow: "diamond",  fill: "filled", at: "target" },
});
export const EDGE_KINDS = Object.freeze(Object.keys(EDGE_STYLE));

export const LANGUAGE_STYLE = Object.freeze({
  ada: { letter: "A", color: "#b45309" },
  c: { letter: "C", color: "#475569" },
  cpp: { letter: "+", color: "#1d4ed8" },
  python: { letter: "P", color: "#15803d" },
});
const FALLBACK_LANGUAGE = { color: "#6b7280" };

/** Small round SVG badge (data URI) for a language; "none" when there is no language. */
export function languageBadge(language) {
  if (!language) return "none";
  const s = LANGUAGE_STYLE[language] || { ...FALLBACK_LANGUAGE, letter: String(language)[0].toUpperCase() };
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">` +
    `<circle cx="8" cy="8" r="7" fill="${s.color}" stroke="#fff" stroke-width="1.5"/>` +
    `<text x="8" y="11.5" font-family="sans-serif" font-size="10" font-weight="700" text-anchor="middle" fill="#fff">${s.letter}</text></svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

// ---- labels --------------------------------------------------------------------------------------------------
export const LABEL_ZOOM_THRESHOLD = 0.6;
export const MAX_LABEL_CHARS = 24;
const LABEL_BASE = Object.freeze({ fontSize: 11, maxWidth: 110, marginY: 4 });

/** On-screen-constant label geometry: Cytoscape scales text with zoom, so divide by it. */
export function labelMetrics(zoom) {
  const z = zoom > 0 ? zoom : 1;
  return { fontSize: LABEL_BASE.fontSize / z, maxWidth: LABEL_BASE.maxWidth / z, marginY: LABEL_BASE.marginY / z };
}

/** Label text to draw: "" when hidden by the zoom policy; ellipsised when long. */
export function labelText(text, { zoom = 1, isFocus = false, emphasised = false } = {}) {
  if (!text) return "";
  if (zoom < LABEL_ZOOM_THRESHOLD && !isFocus && !emphasised) return "";
  return text.length > MAX_LABEL_CHARS ? text.slice(0, MAX_LABEL_CHARS - 1) + "…" : text;
}

// ---- stylesheet ----------------------------------------------------------------------------------------------
const zoomOf = (ele) => ele.cy().zoom();

function nodeRules() {
  const base = {
    selector: "node",
    style: {
      label: (ele) => labelText(ele.data("label"), {
        zoom: zoomOf(ele), isFocus: !!ele.data("isFocus"), emphasised: ele.hasClass("emphasised"),
      }),
      "font-size": (ele) => labelMetrics(zoomOf(ele)).fontSize,
      "text-max-width": (ele) => labelMetrics(zoomOf(ele)).maxWidth,
      "text-margin-y": (ele) => labelMetrics(zoomOf(ele)).marginY,
      "text-valign": "bottom", "text-halign": "center", "text-wrap": "ellipsis",
      color: TOKENS.text,
      "text-background-color": TOKENS.textBg, "text-background-opacity": 0.85,
      "text-background-padding": 1, "text-background-shape": "roundrectangle",
      "background-color": FALLBACK_NODE_STYLE.tint, shape: FALLBACK_NODE_STYLE.shape,
      "border-width": 1.5, "border-color": TOKENS.border, width: 22, height: 22,
      // language badge, top-right, allowed to overhang the node
      "background-image": "data(badge)", "background-fit": "none", "background-clip": "none",
      "background-width": 12, "background-height": 12,
      "background-position-x": "100%", "background-position-y": "0%",
      "background-image-containment": "over", "bounds-expansion": 6,
      "z-index": 10,
    },
  };
  const perKind = Object.entries(NODE_STYLE).map(([kind, s]) => ({
    selector: `node[kind = "${kind}"]`,
    style: { shape: s.shape, "background-color": s.tint },
  }));
  return [
    base, ...perKind,
    { selector: "node[?external]", style: { "border-style": "dashed" } },
    {
      selector: "node[?isFocus]",
      style: { "border-width": 4, "border-color": TOKENS.focusBorder, width: 30, height: 30, "z-index": 99 },
    },
    { selector: "node.emphasised", style: { "border-color": TOKENS.hover, "border-width": 3, "z-index": 50 } },
  ];
}

function edgeRules() {
  const base = {
    selector: "edge",
    style: {
      width: 1.5, "line-color": TOKENS.edgeMuted, "curve-style": "bezier", "arrow-scale": 0.9, opacity: 0.85,
      "z-index": 1, // edges under nodes and their labels
    },
  };
  const perKind = Object.entries(EDGE_STYLE).map(([kind, s]) => ({
    selector: `edge[kind = "${kind}"]`,
    style: {
      width: s.width, "line-style": s.line, "line-color": s.hue,
      [`${s.at}-arrow-shape`]: s.arrow, [`${s.at}-arrow-fill`]: s.fill, [`${s.at}-arrow-color`]: s.hue,
    },
  }));
  return [base, ...perKind];
}

/** Rules for hover emphasis and the legend-driven filter (class `filtered`, applied by the canvas). */
function stateRules() {
  return [
    { selector: "edge.emphasised", style: { opacity: 1, width: 2.5 } },
    { selector: ".filtered", style: { display: "none" } },
  ];
}

/** Full stylesheet: base encoding, then `extraRuleSets` (see header). */
export function buildStylesheet(extraRuleSets = []) {
  const rules = [...nodeRules(), ...edgeRules(), ...stateRules()];
  for (const set of extraRuleSets) {
    const r = typeof set === "function" ? set(TOKENS) : set;
    if (Array.isArray(r)) rules.push(...r);
    else if (r) rules.push(r);
  }
  return rules;
}

export const stylesheet = buildStylesheet();
