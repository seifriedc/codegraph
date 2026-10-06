// Entry point: wires URL state, API, canvas and panel. Plain ES module, no build step.
// Vendored libs (cytoscape, d3) are classic scripts that set window globals; see index.html.
import { fetchHierarchy, fetchNeighborhood, fetchNode } from "./api.js";
import { HIERARCHY_MODES } from "./hierarchy_layout.js";
import { createCanvas } from "./canvas.js";
import { statusText } from "./elements.js";
import { renderPanel } from "./panel.js";
import { depthOptions, MODES, ringText } from "./reach.js";
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
    $("rings").textContent = layered ? "" : ringText(hood.ring_counts, state.depth);
    if (layered) canvas.showHierarchy(hood, state.view);
    else canvas.show(hood);
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

render();
