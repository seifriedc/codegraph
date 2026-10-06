// Entry point: wires URL state, API, canvas and panel. Plain ES module, no build step.
// Vendored libs (cytoscape, d3) are classic scripts that set window globals; see index.html.
import { fetchNeighborhood, fetchNode, fetchOverview } from "./api.js";
import { createCanvas } from "./canvas.js";
import { statusText } from "./elements.js";
import { renderPanel } from "./panel.js";
import { toggleExpanded, overviewStatus } from "./overview-elements.js";
import { createOverviewView, overviewStyle } from "./overview-view.js";
import { formatHash, parseHash, MAX_UI_DEPTH } from "./state.js";

const $ = (id) => document.getElementById(id);

const canvas = createCanvas($("cy"), {
  cytoscape: window.cytoscape,
  d3: window.d3,
  // Clicking a node refocuses on it (pushes a history entry; hashchange does the rendering).
  extraStyle: overviewStyle,
  onTapNode: (id) => {
    if (state.view === "overview") return overviewTap(id);
    if (id !== state.focus) setState({ focus: id }, { push: true });
  },
  onLayoutState: (s) => { $("layout-state").textContent = s === "running" ? "settling" : "settled"; },
});

if (window.cytoscapeFcose) window.cytoscape.use(window.cytoscapeFcose);
const overview = createOverviewView(canvas.cy, {
  tooltip: $("tip"),
  onLayoutState: (s) => { $("layout-state").textContent = s === "running" ? "settling" : "settled"; },
});
canvas.cy.on("tap", (evt) => { if (evt.target === canvas.cy && state.view === "overview") select(null); });

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

// ---- Overview (landing view) ----
let shownView = null;   // which view the canvas currently holds; elements are cleared on a switch
let selected = null;    // {id, nodeId, name} of the selected overview node

function select(data) {
  selected = data ? { id: data.id, nodeId: data.nodeId, name: data.full } : null;
  $("ov-selection").textContent = selected ? selected.name : "";
  $("ov-focus").disabled = !(selected && selected.nodeId);
}

function overviewTap(id) {
  const data = canvas.cy.getElementById(id).data();
  select(data);
  // click expands a collapsed Group in place (and collapses an expanded one)
  if (data.group) setState({ expanded: toggleExpanded(state.expanded, id) });
}

function renderKindFilter(resp) {
  const box = $("ov-kinds");
  box.replaceChildren();
  for (const kind of resp.available_kinds) {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = resp.kinds.includes(kind);
    cb.addEventListener("change", () => {
      const on = new Set(resp.kinds);
      if (cb.checked) on.add(kind); else on.delete(kind);
      setState({ okinds: resp.available_kinds.filter((k) => on.has(k)) });
    });
    label.append(cb, ` ${kind}`);
    box.append(label);
  }
}

async function renderOverview(seq) {
  try {
    const resp = await fetchOverview({ groupBy: state.groupBy, expanded: state.expanded, kinds: state.okinds });
    if (seq !== requestSeq) return;
    $("status").textContent = overviewStatus(resp);
    renderKindFilter(resp);
    renderPanel($("panel"), null);
    overview.show(resp);
    if (selected && !canvas.cy.getElementById(selected.id).length) select(null);
    else if (selected) canvas.cy.getElementById(selected.id).select();
  } catch (err) {
    if (seq === requestSeq) $("status").textContent = `Error: ${err.message}`;
  }
}

function enterView(view) {
  if (shownView === view) return;
  canvas.layout.stop();
  overview.hide();
  canvas.cy.elements().remove();
  select(null);
  document.body.dataset.view = view;
  shownView = view;
  // Hook for the search ticket: fired whenever the landing overview is entered; focus the search box here.
  if (view === "overview") document.dispatchEvent(new CustomEvent("codegraph:landing"));
}

$("ov-focus").addEventListener("click", () => {
  if (selected && selected.nodeId) setState({ view: "focus", focus: selected.nodeId, expanded: [] }, { push: true });
});
$("ov-home").addEventListener("click", () => setState({ view: "overview", focus: null }, { push: true }));

async function render() {
  const seq = ++requestSeq;
  enterView(state.view === "overview" ? "overview" : "focus");
  if (state.view === "overview") return renderOverview(seq);
  $("depth").value = String(state.depth);
  $("direction").value = state.direction;
  if (!state.focus) {
    $("status").textContent = "No focus node. Open the page with #focus=<node id or qualified name>.";
    renderPanel($("panel"), null);
    return;
  }
  try {
    const [hood, detail] = await Promise.all([
      fetchNeighborhood(state.focus, { depth: state.depth, direction: state.direction }),
      fetchNode(state.focus),
    ]);
    if (seq !== requestSeq) return;
    if (!hood || !detail) {
      $("status").textContent = `Node not found: ${state.focus}. Was the database re-indexed?`;
      renderPanel($("panel"), null);
      return;
    }
    $("status").textContent = statusText(hood);
    canvas.show(hood);
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

render();
