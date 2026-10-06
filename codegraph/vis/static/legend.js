// Legend: left-panel kind filters and the collapsible on-canvas mini legend.
// The models are pure; the render functions only touch the document they are given.
import { EDGE_KINDS, EDGE_STYLE, FALLBACK_NODE_STYLE, NODE_KINDS, NODE_STYLE } from "./style.js";
import { isEdgeKindVisible, isNodeKindVisible } from "./filters.js";

/** Count kinds in a neighborhood response: {nodes: {kind: n}, edges: {kind: n}}. */
export function countKinds(resp) {
  const tally = (items) => items.reduce((acc, i) => { acc[i.kind] = (acc[i.kind] || 0) + 1; return acc; }, {});
  return { nodes: tally(resp.nodes || []), edges: tally(resp.edges || []) };
}

function rows(known, present, isVisible, f) {
  const kinds = [...known, ...Object.keys(present).filter((k) => !known.includes(k)).sort()];
  return kinds.map((kind) => ({ kind, count: present[kind] || 0, checked: isVisible(f, kind) }));
}

/** Left-panel model: every known kind (plus unknown kinds present in the data) with count and checked state. */
export function legendModel(filters, counts = { nodes: {}, edges: {} }) {
  return {
    nodes: rows(NODE_KINDS, counts.nodes || {}, isNodeKindVisible, filters),
    edges: rows(EDGE_KINDS, counts.edges || {}, isEdgeKindVisible, filters),
  };
}

/** Mini-legend model: only kinds that are visible (not filtered) and present in the current view. */
export function miniLegendModel(filters, counts) {
  const m = legendModel(filters, counts);
  const keep = (r) => r.checked && r.count > 0;
  return { nodes: m.nodes.filter(keep), edges: m.edges.filter(keep) };
}

// ---- swatches (SVG, 18x18 box) -------------------------------------------------------------------------------
const POINTS = {
  rectangle: [[2, 3], [16, 3], [16, 15], [2, 15]],
  "round-rectangle": [[2, 3], [16, 3], [16, 15], [2, 15]],
  "cut-rectangle": [[2, 5], [5, 2], [16, 2], [16, 13], [13, 16], [2, 16]],
  octagon: [[6, 2], [12, 2], [16, 6], [16, 12], [12, 16], [6, 16], [2, 12], [2, 6]],
  hexagon: [[5, 2], [13, 2], [17, 9], [13, 16], [5, 16], [1, 9]],
  "round-diamond": [[9, 1], [17, 9], [9, 17], [1, 9]],
  diamond: [[9, 1], [17, 9], [9, 17], [1, 9]],
  "round-tag": [[2, 3], [12, 3], [17, 9], [12, 15], [2, 15]],
  tag: [[2, 3], [12, 3], [17, 9], [12, 15], [2, 15]],
  "round-triangle": [[9, 2], [17, 16], [1, 16]],
  triangle: [[9, 2], [17, 16], [1, 16]],
  pentagon: [[9, 1], [17, 7], [14, 16], [4, 16], [1, 7]],
};

/** Polygon points for a Cytoscape shape name, "circle" for ellipse, or null if unsupported. */
export function shapePoints(shape) {
  if (shape === "ellipse") return "circle";
  return POINTS[shape] || null;
}

const SVG_NS = "http://www.w3.org/2000/svg";

function svg(doc, w, h) {
  const s = doc.createElementNS(SVG_NS, "svg");
  s.setAttribute("width", String(w)); s.setAttribute("height", String(h));
  s.setAttribute("viewBox", `0 0 ${w} ${h}`); s.setAttribute("aria-hidden", "true");
  return s;
}
function sub(doc, parent, tag, attrs) {
  const e = doc.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  parent.append(e);
  return e;
}

export function nodeSwatch(doc, kind) {
  const st = NODE_STYLE[kind] || FALLBACK_NODE_STYLE;
  const s = svg(doc, 18, 18);
  const pts = shapePoints(st.shape) || "circle";
  const common = { fill: st.tint, stroke: "#555", "stroke-width": 1.2 };
  if (pts === "circle") sub(doc, s, "circle", { cx: 9, cy: 9, r: 7, ...common });
  else sub(doc, s, "polygon", { points: pts.map((p) => p.join(",")).join(" "), ...common });
  return s;
}

export function edgeSwatch(doc, kind) {
  const st = EDGE_STYLE[kind] || { line: "solid", width: 1, hue: "#9ca3af", arrow: "vee", fill: "filled", at: "target" };
  const s = svg(doc, 30, 12);
  const dash = { dashed: "4 3", dotted: "1.5 2.5", solid: "" }[st.line];
  const x1 = st.at === "source" ? 9 : 1, x2 = st.at === "source" ? 29 : 21;
  const line = { x1, y1: 6, x2, y2: 6, stroke: st.hue, "stroke-width": st.width };
  if (dash) line["stroke-dasharray"] = dash;
  sub(doc, s, "line", line);
  const tip = st.at === "source" ? 1 : 29, dir = st.at === "source" ? 1 : -1; // head drawn at the tip, opening away from it
  const fill = st.fill === "hollow" ? "#fff" : st.hue, head = { fill, stroke: st.hue, "stroke-width": 1 };
  const p = (pts) => pts.map(([dx, y]) => `${tip + dir * dx},${y}`).join(" ");
  if (st.arrow === "triangle") sub(doc, s, "polygon", { points: p([[0, 6], [8, 2], [8, 10]]), ...head });
  else if (st.arrow === "diamond") sub(doc, s, "polygon", { points: p([[0, 6], [4, 2.5], [8, 6], [4, 9.5]]), ...head });
  else if (st.arrow === "circle") sub(doc, s, "circle", { cx: tip + dir * 3, cy: 6, r: 3, ...head });
  else sub(doc, s, "polyline", { points: p([[7, 2], [0, 6], [7, 10]]), fill: "none", stroke: st.hue, "stroke-width": 1.2 });
  return s;
}

function el(doc, tag, text, cls) {
  const e = doc.createElement(tag);
  if (text != null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

function legendSection(doc, title, items, swatch, onToggle) {
  const sec = el(doc, "section", null, "legend-section");
  sec.append(el(doc, "h3", title));
  for (const r of items) {
    const label = el(doc, "label", null, "legend-row" + (r.checked ? "" : " off"));
    const box = el(doc, "input");
    box.type = "checkbox"; box.checked = r.checked; box.dataset.kind = r.kind;
    box.addEventListener("change", () => onToggle(r.kind));
    label.append(box, swatch(doc, r.kind), el(doc, "span", r.kind, "legend-kind"), el(doc, "span", r.count ? String(r.count) : "", "legend-count"));
    sec.append(label);
  }
  return sec;
}

/** Left-panel legend; the checkboxes are the kind filters. */
export function renderLegend(root, model, { onToggleNode, onToggleEdge }, doc = root.ownerDocument) {
  root.replaceChildren(
    legendSection(doc, "Node kinds", model.nodes, nodeSwatch, onToggleNode),
    legendSection(doc, "Edge kinds", model.edges, edgeSwatch, onToggleEdge),
  );
}

/** Collapsible on-canvas legend (a <details>, so collapse state survives re-renders if `open` is passed back). */
export function renderMiniLegend(root, mini, doc = root.ownerDocument) {
  const wasOpen = root.querySelector("details") ? root.querySelector("details").open : true;
  root.replaceChildren();
  if (!mini.nodes.length && !mini.edges.length) return;
  const d = el(doc, "details");
  d.open = wasOpen;
  d.append(el(doc, "summary", "Legend"));
  for (const [items, swatch] of [[mini.nodes, nodeSwatch], [mini.edges, edgeSwatch]]) {
    for (const r of items) {
      const row = el(doc, "div", null, "legend-row");
      row.append(swatch(doc, r.kind), el(doc, "span", r.kind, "legend-kind"));
      d.append(row);
    }
  }
  root.append(d);
}
