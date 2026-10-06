// Entry point: wires URL state, API, canvas and panel. Plain ES module, no build step.
// Vendored libs (cytoscape, d3) are classic scripts that set window globals; see index.html.
import { fetchExpand, fetchHierarchy, fetchNeighborhood, fetchNode, fetchOverview, fetchSearch } from "./api.js";
import { HIERARCHY_MODES } from "./hierarchy_layout.js";
import { createCanvas } from "./canvas.js";
import { toggleEdgeKind, toggleNodeKind } from "./filters.js";
import { countKinds, legendModel, miniLegendModel, renderLegend, renderMiniLegend } from "./legend.js";
import { renderPanel } from "./panel.js";
import { BUDGET, createModel, nextLimit, scaleStatus } from "./scale.js";
import { depthOptions, MODES, ringText } from "./reach.js";
import { createRecent } from "./recent.js";
import { mergeGraphs } from "./search.js";
import { mountSearch } from "./search-ui.js";
import { toggleExpanded, overviewStatus } from "./overview-elements.js";
import { createOverviewView, overviewStyle } from "./overview-view.js";
import { createUrlController, notFoundMessage, replayStubs } from "./urlstate.js";

const $ = (id) => document.getElementById(id);

const canvas = createCanvas($("cy"), {
  cytoscape: window.cytoscape,
  d3: window.d3,
  dagre: window.dagre,
  // Clicking a node refocuses on it (pushes a history entry; hashchange does the rendering).
  styleRules: [overviewStyle],
  onTapNode: (id) => {
    if (url.state.view === "overview") return overviewTap(id);
    if (id !== url.state.focus) setState({ focus: id });
  },
  onTapStub: (stub) => expandStub(stub),
  onLayoutState: (s) => { $("layout-state").textContent = s === "running" ? "settling" : "settled"; },
});

if (window.cytoscapeFcose) window.cytoscape.use(window.cytoscapeFcose);
const overview = createOverviewView(canvas.cy, {
  tooltip: $("tip"),
  onLayoutState: (s) => { $("layout-state").textContent = s === "running" ? "settling" : "settled"; },
});
canvas.cy.on("tap", (evt) => { if (evt.target === canvas.cy && url.state.view === "overview") select(null); });

// The URL is the source of truth for view state; urlstate.js decides push vs replace (see planChange).
const url = createUrlController({
  location, history,
  render: () => render(),
  notice: (text) => { $("trunc").textContent = text; $("trunc").hidden = !text; },
});
const setState = (patch) => url.apply(patch);
const model = createModel(); // focus neighbourhood + accumulated expansions (scale policy)
let layeredView = false; // hierarchy views have no expansion
let baseHood = null; // the last focus-view response (truncated/total for the status line)
const expanding = new Set();
let counts = { nodes: {}, edges: {} };
let requestSeq = 0; // ignore responses that arrive after a newer request

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
  if (data.group) setState({ expanded: toggleExpanded(url.state.expanded, id) });
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

// Directory | Package toggle and externals checkbox. Group ids differ per grouping, so a switch collapses all.
$("ov-groupby").addEventListener("change", (e) => setState({ groupBy: e.target.value, expanded: [] }));
$("ov-externals").addEventListener("change", (e) => setState({ externals: e.target.checked, expanded: [] }));

function syncOverviewControls() {
  $("ov-groupby").value = url.state.groupBy;
  $("ov-externals").checked = url.state.externals;
}

async function renderOverview(seq) {
  syncOverviewControls();
  try {
    const resp = await fetchOverview({ groupBy: url.state.groupBy, expanded: url.state.expanded, kinds: url.state.okinds, externals: url.state.externals });
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
  if (view === "overview") {
    // the legend and kind filters belong to the focus view; the overview has its own kind checkboxes
    $("legend").replaceChildren();
    $("mini-legend").replaceChildren();
    // Landing hook: the search box takes focus whenever the overview is entered.
    document.dispatchEvent(new CustomEvent("codegraph:landing"));
    search.focusInput();
  }
}

$("ov-focus").addEventListener("click", () => {
  if (selected && selected.nodeId) setState({ view: "focus", focus: selected.nodeId, expanded: [] });
});
$("ov-home").addEventListener("click", () => setState({ view: "overview", focus: null }));

function applyFilters(filters) { // replace-state in the URL; visibility only, no refetch
  setState({ filters });
  canvas.setFilters(filters);
  drawLegends();
}

function drawLegends() {
  renderLegend($("legend"), legendModel(url.state.filters, counts), {
    // Filters are client-side visibility toggles (the server's `mode` overrides the `kinds` param).
    onToggleNode: (k) => applyFilters(toggleNodeKind(url.state.filters, k)),
    onToggleEdge: (k) => applyFilters(toggleEdgeKind(url.state.filters, k)),
  });
  renderMiniLegend($("mini-legend"), miniLegendModel(url.state.filters, counts));
}

async function render() {
  const seq = ++requestSeq;
  enterView(url.state.view === "overview" ? "overview" : "focus");
  $("view").value = url.state.view;
  if (url.state.view === "overview") return renderOverview(seq);
  $("depth").value = String(url.state.depth);
  $("mode").value = url.state.mode;
  $("view").value = url.state.view;
  $("rings").textContent = "";
  canvas.setFilters(url.state.filters); // kind filters come from the URL (also after Back/Forward)
  if (!url.state.focus) {
    $("status").textContent = "No focus node. Open the page with #focus=<node id or qualified name>.";
    renderPanel($("panel"), null);
    return;
  }
  try {
    const layered = HIERARCHY_MODES.includes(url.state.view);
    const [hood, detail] = await Promise.all([
      layered
        ? fetchHierarchy(url.state.focus, { mode: url.state.view, limit: url.state.limit })
        : fetchNeighborhood(url.state.focus, { depth: url.state.depth, mode: url.state.mode, limit: url.state.limit, perNodeCap: BUDGET.fanOut }),
      fetchNode(url.state.focus),
    ]);
    if (seq !== requestSeq) return;
    if (!hood || !detail) { // a stale link: say so, offer search, never fall back to the overview
      canvas.layout.stop();
      canvas.cy.elements().remove();
      baseHood = null;
      counts = { nodes: {}, edges: {} };
      drawLegends();
      $("status").textContent = notFoundMessage(url.state.focus);
      renderPanel($("panel"), null);
      search.focusInput();
      return;
    }
    baseHood = hood;
    layeredView = layered;
    $("rings").textContent = layered ? "" : ringText(hood.ring_counts, url.state.depth);
    if (layered) {
      canvas.showHierarchy(hood, url.state.view);
    } else {
      model.reset(hood);
      const replayed = await replayStubs(model, url.state.stubs, (stub) => fetchExpand(stub, undefined, BUDGET.fanOut),
        () => seq === requestSeq);
      if (seq !== requestSeq) return;
      if (replayed.length !== url.state.stubs.length) setState({ stubs: replayed }); // drop stale ids
      canvas.show(model.view());
    }
    updateScaleUi();
    renderPanel($("panel"), detail);
  } catch (err) {
    if (seq === requestSeq) $("status").textContent = `Error: ${err.message}`;
  }
}

/** Status line, raise-limit control, undo button and the 300-node warning, from the model. */
function updateScaleUi() {
  if (!baseHood) return;
  counts = countKinds(layeredView ? baseHood : model.view());
  drawLegends();
  $("status").textContent = scaleStatus({
    shown: layeredView ? baseHood.nodes.length : model.size, total: baseHood.total,
    truncated: baseHood.truncated, expanded: !layeredView && model.canUndo(),
  });
  const raise = $("raise-limit"), canRaise = baseHood.truncated && url.state.limit < BUDGET.maxLimit;
  raise.hidden = !canRaise;
  if (canRaise) raise.textContent = `Raise limit to ${nextLimit(url.state.limit)}`;
  $("undo").disabled = layeredView || !model.canUndo();
  $("warn").hidden = layeredView || !model.overWarning();
  if (!$("warn").hidden) $("warn-text").textContent = `${model.size} nodes on screen: the graph is getting crowded.`;
}

/** Click on a Stub node: page in its hidden neighbours, merge, highlight what is new. */
async function expandStub(stub) {
  if (layeredView || expanding.has(stub.id)) return;
  expanding.add(stub.id);
  const seq = requestSeq;
  try {
    const page = await fetchExpand(stub, undefined, BUDGET.fanOut);
    if (seq !== requestSeq || !page) return; // refocused meanwhile, or owner vanished
    const { added, budgetHit } = model.expand(stub.id, page);
    setState({ stubs: [...url.state.stubs, stub.id] }); // replace-state: replayed in order on load
    canvas.show(model.view(), { anchor: stub.owner, highlight: added, expansion: true });
    updateScaleUi();
    if (budgetHit) $("status").textContent += `. Node limit (${BUDGET.maxLimit}) reached: prune or undo to continue.`;
  } catch (err) {
    $("status").textContent = `Error: ${err.message}`;
  } finally {
    expanding.delete(stub.id);
  }
}

for (const o of depthOptions()) $("depth").append(new Option(o.label, String(o.value)));
for (const m of MODES) $("mode").append(new Option(m.label, m.value));
$("depth").addEventListener("change", (e) => setState({ depth: Number(e.target.value) }));
$("mode").addEventListener("change", (e) => setState({ mode: e.target.value }));
$("view").addEventListener("change", (e) => setState({ view: e.target.value }));
$("raise-limit").addEventListener("click", () => setState({ limit: nextLimit(url.state.limit) }));
$("undo").addEventListener("click", () => {
  if (!model.undo()) return;
  setState({ stubs: url.state.stubs.slice(0, -1) });
  canvas.show(model.view(), { expansion: true });
  updateScaleUi();
});
$("prune").addEventListener("click", () => {
  model.prune();
  setState({ stubs: [] });
  canvas.show(model.view());
  updateScaleUi();
});
$("recenter").addEventListener("click", () => canvas.recenter());
addEventListener("hashchange", () => url.onHashChange());

drawLegends();
let storage;
try { storage = window.localStorage; } catch { storage = undefined; } // even reading it can throw
export const search = mountSearch($("search"), {
  fetchFn: fetchSearch,
  recent: createRecent(storage),
  onFocus: (n) => setState({ focus: n.id }), // Enter: replace the Focus node
  onAdd: async (n) => { // Shift-Enter: add the node's neighborhood to what is on the canvas
    try {
      const added = await fetchNeighborhood(n.id, { depth: url.state.depth, mode: url.state.mode });
      if (!added || !baseHood || layeredView) return; // merging only applies to the focus view
      const merged = mergeGraphs(model.view(), added);
      const seen = new Set((model.view().stubs || []).map((x) => x.id));
      merged.stubs = [...model.view().stubs, ...(added.stubs || []).filter((x) => !seen.has(x.id))];
      const before = new Set(model.view().nodes.map((x) => x.id));
      const { dropped } = model.adopt(merged);
      baseHood = { ...baseHood, truncated: baseHood.truncated || merged.truncated || dropped > 0 };
      canvas.show(model.view(), { anchor: n.id, expansion: true,
        highlight: model.view().nodes.filter((x) => !before.has(x.id)).map((x) => x.id) });
      updateScaleUi();
    } catch (err) { $("status").textContent = `Error: ${err.message}`; }
  },
});

render();
