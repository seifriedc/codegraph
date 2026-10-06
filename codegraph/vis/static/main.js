// Entry point: wires URL state, API, canvas and panel. Plain ES module, no build step.
// Vendored libs (cytoscape, d3) are classic scripts that set window globals; see index.html.
import { fetchHierarchy, fetchNeighborhood, fetchNode, fetchSearch } from "./api.js";
import { HIERARCHY_MODES } from "./hierarchy_layout.js";
import { createCanvas } from "./canvas.js";
import { statusText } from "./elements.js";
import { defaultFilters, toggleEdgeKind, toggleNodeKind } from "./filters.js";
import { countKinds, legendModel, miniLegendModel, renderLegend, renderMiniLegend } from "./legend.js";
import { renderPanel } from "./panel.js";
import { depthOptions, MODES, ringText } from "./reach.js";
import { createRecent } from "./recent.js";
import { mergeGraphs } from "./search.js";
import { mountSearch } from "./search-ui.js";
import { formatHash, parseHash } from "./state.js";

const $ = (id) => document.getElementById(id);

const canvas = createCanvas($("cy"), {
  cytoscape: window.cytoscape,
  d3: window.d3,
  dagre: window.dagre,
  // Clicking a node refocuses on it (pushes a history entry; hashchange does the rendering).
  onTapNode: (id) => { if (id !== state.focus) setState({ focus: id }, { push: true }); },
  onLayoutState: (s) => { $("layout-state").textContent = s === "running" ? "settling" : "settled"; },
});

let state = parseHash(location.hash);
let filters = defaultFilters(); // kind filters (legend); the URL-state ticket persists these via filtersToParams
let counts = { nodes: {}, edges: {} };
let lastHood = null; // last graph shown, so Shift-Enter search results can be merged into it
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
    // Filters are client-side visibility toggles (the server's `mode` overrides the `kinds` param).
    onToggleNode: (k) => { filters = toggleNodeKind(filters, k); canvas.setFilters(filters); drawLegends(); },
    onToggleEdge: (k) => { filters = toggleEdgeKind(filters, k); canvas.setFilters(filters); drawLegends(); },
  });
  renderMiniLegend($("mini-legend"), miniLegendModel(filters, counts));
}

async function render() {
  const seq = ++requestSeq;
  $("depth").value = String(state.depth);
  $("mode").value = state.mode;
  $("view").value = state.view;
  $("rings").textContent = "";
  if (!state.focus) {
    $("status").textContent = "No focus node. Open the page with #focus=<node id or qualified name>.";
    renderPanel($("panel"), null);
    return;
  }
  try {
    const layered = HIERARCHY_MODES.includes(state.view);
    const [hood, detail] = await Promise.all([
      layered
        ? fetchHierarchy(state.focus, { mode: state.view })
        : fetchNeighborhood(state.focus, { depth: state.depth, mode: state.mode }),
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
    lastHood = layered ? null : hood; // Shift-Enter merging only applies to the focus view
    $("rings").textContent = layered ? "" : ringText(hood.ring_counts, state.depth);
    if (layered) canvas.showHierarchy(hood, state.view);
    else canvas.show(hood);
    drawLegends();
    renderPanel($("panel"), detail);
  } catch (err) {
    if (seq === requestSeq) $("status").textContent = `Error: ${err.message}`;
  }
}

for (const o of depthOptions()) $("depth").append(new Option(o.label, String(o.value)));
for (const m of MODES) $("mode").append(new Option(m.label, m.value));
$("depth").addEventListener("change", (e) => setState({ depth: Number(e.target.value) }));
$("mode").addEventListener("change", (e) => setState({ mode: e.target.value }));
$("view").addEventListener("change", (e) => setState({ view: e.target.value }));
$("recenter").addEventListener("click", () => canvas.recenter());
addEventListener("hashchange", () => { state = parseHash(location.hash); render(); });

drawLegends();
let storage;
try { storage = window.localStorage; } catch { storage = undefined; } // even reading it can throw
export const search = mountSearch($("search"), {
  fetchFn: fetchSearch,
  recent: createRecent(storage),
  onFocus: (n) => setState({ focus: n.id }, { push: true }), // Enter: replace the Focus node
  onAdd: async (n) => { // Shift-Enter: add the node's neighborhood to what is on the canvas
    try {
      const added = await fetchNeighborhood(n.id, { depth: state.depth, mode: state.mode });
      if (!added || !lastHood) return;
      lastHood = mergeGraphs(lastHood, added);
      $("status").textContent = statusText(lastHood);
      canvas.show(lastHood);
    } catch (err) { $("status").textContent = `Error: ${err.message}`; }
  },
});

render();
