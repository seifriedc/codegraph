// Entry point: wires URL state, API, canvas and panel. Plain ES module, no build step.
// Vendored libs (cytoscape, d3) are classic scripts that set window globals; see index.html.
import { fetchExpand, fetchNeighborhood, fetchNode } from "./api.js";
import { createCanvas } from "./canvas.js";
import { renderPanel } from "./panel.js";
import { BUDGET, createModel, nextLimit, scaleStatus } from "./scale.js";
import { formatHash, parseHash, MAX_UI_DEPTH } from "./state.js";

const $ = (id) => document.getElementById(id);

const canvas = createCanvas($("cy"), {
  cytoscape: window.cytoscape,
  d3: window.d3,
  // Clicking a node refocuses on it (pushes a history entry; hashchange does the rendering).
  onTapNode: (id) => { if (id !== state.focus) setState({ focus: id }, { push: true }); },
  onTapStub: (stub) => expandStub(stub),
  onLayoutState: (s) => { $("layout-state").textContent = s === "running" ? "settling" : "settled"; },
});

let state = parseHash(location.hash);
const model = createModel(); // focus neighbourhood + accumulated expansions (scale policy)
let baseHood = null; // the last focus-view response (truncated/total for the status line)
const expanding = new Set();
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
  $("direction").value = state.direction;
  if (!state.focus) {
    $("status").textContent = "No focus node. Open the page with #focus=<node id or qualified name>.";
    renderPanel($("panel"), null);
    return;
  }
  try {
    const [hood, detail] = await Promise.all([
      fetchNeighborhood(state.focus, { depth: state.depth, direction: state.direction, limit: state.limit, perNodeCap: BUDGET.fanOut }),
      fetchNode(state.focus),
    ]);
    if (seq !== requestSeq) return;
    if (!hood || !detail) {
      $("status").textContent = `Node not found: ${state.focus}. Was the database re-indexed?`;
      renderPanel($("panel"), null);
      return;
    }
    baseHood = hood;
    model.reset(hood);
    canvas.show(model.view());
    updateScaleUi();
    renderPanel($("panel"), detail);
  } catch (err) {
    if (seq === requestSeq) $("status").textContent = `Error: ${err.message}`;
  }
}

/** Status line, raise-limit control, undo button and the 300-node warning, from the model. */
function updateScaleUi() {
  if (!baseHood) return;
  $("status").textContent = scaleStatus({
    shown: model.size, total: baseHood.total, truncated: baseHood.truncated, expanded: model.canUndo(),
  });
  const raise = $("raise-limit"), canRaise = baseHood.truncated && state.limit < BUDGET.maxLimit;
  raise.hidden = !canRaise;
  if (canRaise) raise.textContent = `Raise limit to ${nextLimit(state.limit)}`;
  $("undo").disabled = !model.canUndo();
  $("warn").hidden = !model.overWarning();
  if (model.overWarning()) $("warn-text").textContent = `${model.size} nodes on screen: the graph is getting crowded.`;
}

/** Click on a Stub node: page in its hidden neighbours, merge, highlight what is new. */
async function expandStub(stub) {
  if (expanding.has(stub.id)) return;
  expanding.add(stub.id);
  const seq = requestSeq;
  try {
    const page = await fetchExpand(stub, undefined, BUDGET.fanOut);
    if (seq !== requestSeq || !page) return; // refocused meanwhile, or owner vanished
    const { added, budgetHit } = model.expand(stub.id, page);
    canvas.show(model.view(), { anchor: stub.owner, highlight: added, expansion: true });
    updateScaleUi();
    if (budgetHit) $("status").textContent += `. Node limit (${BUDGET.maxLimit}) reached: prune or undo to continue.`;
  } catch (err) {
    $("status").textContent = `Error: ${err.message}`;
  } finally {
    expanding.delete(stub.id);
  }
}

for (let d = 1; d <= MAX_UI_DEPTH; d++) $("depth").append(new Option(String(d), String(d)));
$("depth").addEventListener("change", (e) => setState({ depth: Number(e.target.value) }));
$("direction").addEventListener("change", (e) => setState({ direction: e.target.value }));
$("raise-limit").addEventListener("click", () => setState({ limit: nextLimit(state.limit) }));
$("undo").addEventListener("click", () => {
  if (!model.undo()) return;
  canvas.show(model.view(), { expansion: true });
  updateScaleUi();
});
$("prune").addEventListener("click", () => {
  model.prune();
  canvas.show(model.view());
  updateScaleUi();
});
$("recenter").addEventListener("click", () => canvas.recenter());
addEventListener("hashchange", () => { state = parseHash(location.hash); render(); });

render();
