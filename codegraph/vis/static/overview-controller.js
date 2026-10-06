// The Overview screen's controller: selection, kind checkboxes, group-by / externals controls and the
// render of one /api/overview response. DOM access goes through the injected `$` (id -> element).
import { overviewStatus, toggleExpanded } from "./overview-elements.js";

export function createOverviewController({ $, canvas, overview, url, setState, fetchOverview, renderPanel, isCurrent }) {
  let selected = null; // {id, nodeId, name} of the selected overview node

  function select(data) {
    selected = data ? { id: data.id, nodeId: data.nodeId, name: data.full } : null;
    $("ov-selection").textContent = selected ? selected.name : "";
    $("ov-focus").disabled = !(selected && selected.nodeId);
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
      renderPanel($("panel"), null);
      overview.show(resp);
      if (selected && !canvas.cy.getElementById(selected.id).length) select(null);
      else if (selected) canvas.cy.getElementById(selected.id).select();
    } catch (err) {
      if (isCurrent(seq)) $("status").textContent = `Error: ${err.message}`;
    }
  }

  // Directory | Package toggle and externals checkbox. Group ids differ per grouping, so a switch collapses all.
  $("ov-groupby").addEventListener("change", (e) => setState({ groupBy: e.target.value, expanded: [] }));
  $("ov-externals").addEventListener("change", (e) => setState({ externals: e.target.checked, expanded: [] }));
  $("ov-focus").addEventListener("click", () => {
    if (selected && selected.nodeId) setState({ view: "focus", focus: selected.nodeId, expanded: [] });
  });
  $("ov-home").addEventListener("click", () => setState({ view: "overview", focus: null }));
  // clicking empty canvas clears the selection
  canvas.cy.on("tap", (evt) => { if (evt.target === canvas.cy && url.state.view === "overview") select(null); });

  return { select, tap, render };
}
