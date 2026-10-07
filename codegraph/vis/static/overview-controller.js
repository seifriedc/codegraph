// The Overview screen's controller: selection, kind checkboxes, group-by / externals controls and the
// render of one /api/overview response. DOM access goes through the injected `$` (id -> element).
import { overviewStatus, toggleExpanded } from "./overview-elements.js";

export function createOverviewController({ $, canvas, overview, url, setState, fetchOverview, fetchNode, renderPanel, isCurrent, onError }) {
  let selected = null; // {id, nodeId, name} of the selected overview node

  function select(data) {
    selected = data ? { id: data.id, nodeId: data.nodeId, name: data.full } : null;
    $("ov-focus").disabled = !(selected && selected.nodeId);
    showDetails(selected);
  }

  /** Fill the Details panel for the selection; Groups have no node, so they (and no selection) show the placeholder. */
  async function showDetails(sel) {
    renderPanel($("details"), null);
    if (!sel || !sel.nodeId) return;
    try {
      const detail = await fetchNode(sel.nodeId);
      if (selected === sel && detail) renderPanel($("details"), detail); // drop a response for an earlier click
    } catch (err) {
      if (selected === sel) onError(err);
    }
  }

  /** Click on an overview node: select it; a Group also expands (or collapses) in place. */
  function tap(id) {
    const data = canvas.cy.getElementById(id).data();
    select(data);
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

  /** Render the overview for the current URL state. `seq` is checked through `isCurrent(seq)` after the fetch. */
  async function render(seq) {
    $("ov-groupby").value = url.state.groupBy;
    $("ov-externals").checked = url.state.externals;
    try {
      const resp = await fetchOverview({ groupBy: url.state.groupBy, expanded: url.state.expanded, kinds: url.state.okinds, externals: url.state.externals });
      if (!isCurrent(seq)) return;
      $("status").textContent = overviewStatus(resp);
      renderKindFilter(resp);
      overview.show(resp);
      if (selected && !canvas.cy.getElementById(selected.id).length) select(null);
      else if (selected) canvas.cy.getElementById(selected.id).select();
    } catch (err) {
      if (isCurrent(seq)) onError(err);
    }
  }

  // Directory | Package toggle and externals checkbox. Group ids differ per grouping, so a switch collapses all.
  $("ov-groupby").addEventListener("change", (e) => setState({ groupBy: e.target.value, expanded: [] }));
  $("ov-externals").addEventListener("change", (e) => setState({ externals: e.target.checked, expanded: [] }));
  $("ov-focus").addEventListener("click", () => {
    if (selected && selected.nodeId) setState({ view: "focus", focus: selected.nodeId, expanded: [] });
  });
  // clicking empty canvas clears the selection
  canvas.cy.on("tap", (evt) => { if (evt.target === canvas.cy && url.state.view === "overview") select(null); });

  /** The selected node id (null for no selection or a Group): what a switch to another View should focus on. */
  const selectedNodeId = () => (selected && selected.nodeId) || null;

  return { select, tap, render, selectedNodeId };
}
