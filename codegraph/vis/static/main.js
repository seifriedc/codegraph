// Entry point: wires URL state, API, canvas and panel. Plain ES module, no build step.
// Vendored libs (cytoscape, d3) are classic scripts that set window globals; see index.html.
import { fetchNeighborhood, fetchNode } from "./api.js";
import { createCanvas } from "./canvas.js";
import { statusText } from "./elements.js";
import { defaultFilters, edgeKindsParam, toggleEdgeKind, toggleNodeKind } from "./filters.js";
import { countKinds, legendModel, miniLegendModel, renderLegend, renderMiniLegend } from "./legend.js";
import { renderPanel } from "./panel.js";
import { formatHash, parseHash, MAX_UI_DEPTH } from "./state.js";

const $ = (id) => document.getElementById(id);

const canvas = createCanvas($("cy"), {
  cytoscape: window.cytoscape,
  d3: window.d3,
  // Clicking a node refocuses on it (pushes a history entry; hashchange does the rendering).
  onTapNode: (id) => { if (id !== state.focus) setState({ focus: id }, { push: true }); },
  onLayoutState: (s) => { $("layout-state").textContent = s === "running" ? "settling" : "settled"; },
});

let state = parseHash(location.hash);
let filters = defaultFilters(); // kind filters (legend); the URL-state ticket persists these via filtersToParams
let counts = { nodes: {}, edges: {} };
let requestSeq = 0; // ignore responses that arrive after a newer request

function setState(patch, { push = false } = {}) {
  state = { ...state, ...patch };
  const hash = formatHash(state);
  if (hash !== location.hash) {
    // push for focus changes, replace for depth/direction tweaks; hashchange re-renders either way
    if (push) location.hash = hash || "#";
    else history.replaceState(null, "", hash || location.pathname);
  }
  if (!push) render();
}

function drawLegends() {
  renderLegend($("legend"), legendModel(filters, counts), {
    // node kinds filter client-side only; edge kinds also change the API request
    onToggleNode: (k) => { filters = toggleNodeKind(filters, k); canvas.setFilters(filters); drawLegends(); },
    onToggleEdge: (k) => { filters = toggleEdgeKind(filters, k); render(); },
  });
  renderMiniLegend($("mini-legend"), miniLegendModel(filters, counts));
}

async function render() {
  const seq = ++requestSeq;
  $("depth").value = String(state.depth);
  $("direction").value = state.direction;
  if (!state.focus) {
    $("status").textContent = "No focus node. Open the page with #focus=<node id or qualified name>.";
    renderPanel($("panel"), null);
    return;
  }
  try {
    const [hood, detail] = await Promise.all([
      fetchNeighborhood(state.focus, { depth: state.depth, direction: state.direction, kinds: edgeKindsParam(filters) }),
      fetchNode(state.focus),
    ]);
    if (seq !== requestSeq) return;
    if (!hood || !detail) {
      $("status").textContent = `Node not found: ${state.focus}. Was the database re-indexed?`;
      renderPanel($("panel"), null);
      return;
    }
    $("status").textContent = statusText(hood);
    counts = countKinds(hood);
    canvas.show(hood);
    canvas.setFilters(filters);
    drawLegends();
    renderPanel($("panel"), detail);
  } catch (err) {
    if (seq === requestSeq) $("status").textContent = `Error: ${err.message}`;
  }
}

for (let d = 1; d <= MAX_UI_DEPTH; d++) $("depth").append(new Option(String(d), String(d)));
$("depth").addEventListener("change", (e) => setState({ depth: Number(e.target.value) }));
$("direction").addEventListener("change", (e) => setState({ direction: e.target.value }));
$("recenter").addEventListener("click", () => canvas.recenter());
addEventListener("hashchange", () => { state = parseHash(location.hash); render(); });

drawLegends();
render();
