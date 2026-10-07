# Graph visualization: verification guide

How `codegraph serve` is verified beyond the automated tests: the API contract guard, the
acceptance demo, the manual physics and layout checklist, and the known limitations of v1.

Automated coverage: `pytest` (API, packaging, Graph primitives) and `node --test tests/js/*.test.mjs`
(pure client logic). Neither exercises a real browser; the checklist below does.

## API contract guard

`tests/test_openapi_snapshot.py` compares the FastAPI-generated OpenAPI schema with the committed
`tests/snapshots/openapi.json`. Any API change (route, parameter, response field) fails it.

When it fails:

1. Update the JS client by hand: `codegraph/vis/static/api.js` and every caller affected.
2. Regenerate the snapshot (one command):

   ```bash
   pytest tests/test_openapi_snapshot.py --update-openapi-snapshot
   ```

3. Review the snapshot diff and commit it together with the client change.

`tests/test_packaging.py` builds the wheel and asserts that every file under `codegraph/vis/static/`
(modules and `vendor/` libraries) ships in it; `tests/test_serve_api.py` asserts `GET /` and every
script the page references are served.

## Acceptance demo

The end-to-end check that the UI and the API agree.

```bash
codegraph index tests/fixtures/cpp --db /tmp/demo.duckdb
codegraph serve --db /tmp/demo.duckdb        # then open http://127.0.0.1:8000
```

1. The Overview loads with the search box focused. Type `Shape`, pick the C++ class `Shape`
   (Enter). The URL becomes `#focus=<id>`.
2. Confirm the type hierarchy: switch View to "type hierarchy". `Shape` is the root with exactly
   two children, `Circle` and `Rectangle`, joined by hollow-triangle `inherits` edges.
   (API equivalent: `GET /api/hierarchy/Shape?mode=type` returns `{Shape, Circle, Rectangle}`.)
3. Back in the focus view, select `Shape` and read the side panel's Neighbors table. It must equal
   the expected counts asserted in `tests/test_serve_neighborhood.py::test_node_detail_has_path_defining_files_and_neighbor_counts`
   (the single source of the expected numbers):

   | kind     | in | out |
   |----------|----|-----|
   | contains | 1  | 2   |
   | inherits | 2  | 0   |

4. Defined in lists `cpp/shapes.cpp` only (Path `cpp/shapes.cpp:<line>`).

Indexing the whole `tests/fixtures` tree gives the same numbers for `Shape`.

## Manual physics and layout checklist

Run before a release, in a real browser, after the demo has been set up. Items marked "(whole fixtures)"
need `codegraph index tests/fixtures --db /tmp/all.duckdb`. Nothing here has been verified in a
browser by the implementers: treat the first run as the first real verification, and file an issue
for every failure.

### Loading and landing

- [ ] A bare URL (no hash) opens the Overview (whole fixtures); the search box has focus; depth, mode and view-specific controls are hidden.
- [ ] `#focus=Shape` loads directly; status line shows node and edge counts; the layout indicator goes "settling" then "settled".
- [ ] A bad id (`#focus=nope`) shows "Node not found: nope. Was the database re-indexed? Use search to find it again." and the search box stays usable; no blank page, no console error loop.

### Search keyboard flow

- [ ] `/` and Ctrl/Cmd-K focus the search box from anywhere except while typing in an input; they do not insert a character.
- [ ] With an empty box, the dropdown shows "Recent" nodes (after you have visited some); one character shows "Type at least 2 characters".
- [ ] Typing shows ranked results with kind and path; the exact-name class ranks above same-named type nodes; a miss shows "No matches".
- [ ] Up/Down move the highlighted row (scrolling it into view); Enter replaces the Focus node; Escape clears and closes. Enter with an empty box does nothing.
- [ ] Shift-Enter adds the result's neighborhood to the canvas without changing the Focus node (focus views only).

### Show mode and Direction (focus views)

- [ ] The default Show mode is "Neighborhood (all edges)" (URL has no `mode` key); the Direction select is enabled and set to "both".
- [ ] Focus a file node: the Neighborhood shows its contained functions and classes (`contains` edges); a package focus shows its members. Neither is nearly empty.
- [ ] Direction "out" shows only what the Focus node points to, "in" only what points to it; the choice is stored as `direction=` in the URL, survives reload, and Back/forward restores it (it replaces the history entry).
- [ ] Switching Show to Impact set, Dependencies or Impact + dependencies disables the Direction select (those modes fix their own direction and edge kinds); switching back re-enables it with the previous value.
- [ ] A hand-edited `kinds=inherits,contains` in the URL restricts the fetched edges to those kinds in Neighborhood mode (the legend filters remain client-side visibility only and never refetch).

### Fit

- [ ] After panning and zooming far away, Fit fits every node in view with comfortable margins.
- [ ] After expanding a node that adds nodes off-screen, Fit brings them in view.
- [ ] Fit does not move any node or restart the layout.

### Physics, bounded settle time and pinned focus

- [ ] A focus view settles on its own within about 4 seconds even at the 300-node warning size; the indicator returns to "settled" and the CPU goes idle (no continuous animation).
- [ ] The Focus node stays where it is (pinned) while neighbors settle around it; it never drifts when other nodes are dragged.
- [ ] Dragging a node wakes the layout ("settling"), neighbors follow, and it re-sleeps shortly after release; a dragged Focus node stays where it is dropped.
- [ ] Refocusing (choosing another node) keeps positions of nodes that stay on screen; they do not scatter and re-settle from scratch.
- [ ] Positions stay stable while kind filters are toggled.
- [ ] Hierarchy views (type/declaration hierarchy) draw a layered top-down tree with no physics ("settled" immediately).

### Expansion, undo and highlight

- [ ] Clicking a Stub node (a node showing it has hidden neighbors) pages in those neighbors next to it; new nodes and edges are highlighted briefly, then the highlight fades.
- [ ] Undo expand removes exactly the last expansion (nodes and edges), restores the previous view, and disables itself when nothing is left to undo. Repeated undo walks back one step at a time.
- [ ] Expanding past the node budget stops with "Node limit (500) reached: prune or undo to continue." and at 300 nodes the Alert button turns amber; its popover lists the crowded-graph message with a "Prune to focus neighborhood" button that drops all expansions.
- [ ] Reload and Back/forward restore the expansion state from the URL (see URL behaviour).

### Stub nodes and truncation

- [ ] High-degree nodes show a Stub indicating how many neighbors are hidden; a stub never counts as a real node (no Focus, no side panel).
- [ ] When the neighborhood is truncated, the status line says "of at least N" (the walk stops at the budget, so the total is a lower bound), and "Raise limit to N" appears; raising it refetches and discards expansions (see Known limitations).
- [ ] Ring counts (Impact / Dependencies modes) are shown next to the controls; when the view is truncated, rings the walk never reached are not listed ("deeper rings not counted") instead of showing 0.
- [ ] A type or declaration hierarchy bigger than the limit keeps the focus and the shallow rings (children before grandchildren), never an arbitrary slice by name.

### Visual encoding, labels, legend and filters

- [ ] Each node kind has a distinct shape and tint; the graph is still readable in a greyscale screenshot.
- [ ] Each node has a small round language badge at top-right (A / + / C / P; grey letter for other languages); nodes without a language have none.
- [ ] External placeholder nodes have a dashed outline.
- [ ] Edges: calls solid with filled triangle; inherits solid with hollow triangle; imports dashed; references thin dotted grey; instantiates with diamond head; contains with a hollow diamond at the source. Hues differ per kind.
- [ ] Labels keep the same on-screen size while zooming; long names end in an ellipsis.
- [ ] Zoomed out below about 0.6, only the Focus node is labelled; hovering a node labels it and its neighbors and highlights them.
- [ ] Labels have a white backing and edges pass beneath them (no edge/label overlap). Labels are readable at default zoom on a 100-node graph.
- [ ] Left-panel legend lists every node and edge kind with counts for the current view; unchecking a node kind hides those nodes and their edges at once (the Focus node never hides).
- [ ] Unchecking an edge kind hides it without a network request (visibility only).
- [ ] The on-canvas mini legend (bottom-left) shows only visible and present kinds, and collapses and expands.

### Overview with Directory and Package grouping (whole fixtures)

- [ ] Top level shows `ada`, `c`, `cpp` Groups (labelled with sizes) and one external Group; edges have arrowheads and log-scaled thickness.
- [ ] `calls` is unchecked in the kind filter; ticking it adds edges; unticking an edge kind re-aggregates (thickness changes, empty pairs disappear).
- [ ] Hovering an edge shows source, target and per-kind counts (for example `calls: 2, references: 1`).
- [ ] Clicking a collapsed Group expands it in place (a box around its files, other Groups stay put); clicking an expanded box collapses it. Back/forward and reload keep the expansion.
- [ ] Expanding a file shows its functions and classes inside it; selecting a node with a real id enables Focus, which opens `#focus=<id>`; the Overview button returns.
- [ ] "Group by: Package" regroups Ada by Package; C and C++ files appear as files; switching back restores Directory grouping.
- [ ] The externals checkbox adds or removes the external Group (default off).
- [ ] Choosing a search result from the Overview switches to the focus view.
- [ ] Expanding a Group with more than 150 members shows the first 150 only and the status line says "members capped: showing 150 of N"; edges to hidden members are not drawn.
- [ ] Group ids in the URL (`expanded=dir:ada`) are relative to the indexed root: no absolute server path appears in the URL or in any API response.

### URL deep-link and Back behaviour

- [ ] Copying a focus URL into a new tab reproduces the same view (focus, depth, mode, filters, expansions).
- [ ] Changing Focus, View, Mode or Group by adds a history entry; Back steps through exactly these.
- [ ] Changing depth, filters, limit or expanding a node replaces the current entry (Back does not step through them).
- [ ] After Back, the previous Focus node is selected and the side panel matches it.
- [ ] A hand-edited hash with more than 50 expanded ids is capped and a notice says so.

### Toolbar, Controls panel, Details panel and Alert button
- [ ] Switching between Overview, Focus and the hierarchy views never moves the search box, View dropdown, Fit, Undo expand or the Alert button.
- [ ] The Controls panel shows the Legend on top and the View controls pinned at the bottom: Group by, externals and edge kinds in the Overview; Show, Direction and Depth otherwise.
- [ ] The Details panel keeps its Status section (counts, nodes per ring, settling/settled) visible at the bottom while the details above scroll.
- [ ] In the Overview the Focus button sits at the top of the Details panel and is enabled only when a node is selected.
- [ ] The Alert button is grey with nothing to report. A fetch failure turns it red; the crowded-graph and truncated-URL messages turn it amber. A count badge shows how many messages there are.
- [ ] Clicking it opens a popover; clicking outside closes it. "x" dismisses one message and "Clear all" dismisses all. A dismissed message stays hidden while its condition persists and returns after the condition clears and recurs.
- [ ] Choosing "focus" (or a hierarchy view) in the View dropdown with a node selected in the Overview focuses that node. With nothing selected, or a Group selected, the canvas shows "No focus node. Select a node in the overview, or search for one."

## Known limitations in v1

- Same-named entities merge into one node, so an Ada package and a C++ class with the same name share an id and neighbors. Tracked in [#14](https://github.com/seifriedc/codegraph/issues/14).
- C++ namespaces are not Groups in the Overview (Package grouping covers Ada only). Tracked in [#10](https://github.com/seifriedc/codegraph/issues/10).
- The UI has never been exercised in a real browser by its implementers. The checklist above is the first real verification and must be run before release.
- In focus views `contains` is drawn as an ordinary edge with a hollow diamond, not as nesting.
- Shift-Enter "add to canvas" does nothing in hierarchy views, and Shift-Enter merges are not stored in the URL.
- Expansion pages only add edges to the owner node until the view is refetched.
- The node limit is applied while walking, so once a view is truncated `total` and the ring counts are lower bounds: the walk stops at the ring that overflows the budget and deeper rings are never counted.
- The Overview caps member nodes (150 by default, server maximum 500) but not Groups themselves; a directory with thousands of files still draws all of them as Groups. Edges to capped members are dropped.
- Raising the node limit refetches and discards expansions.
- The Overview `externals` API parameter now defaults to false.
- Static HTML export is a later addition.
- Playwright end-to-end tests (including DB-versus-visualization checks) are not written. Tracked in [#15](https://github.com/seifriedc/codegraph/issues/15).
- Clicking a node in the Overview only selects it; it does not set the Focus node. The selection is the pending focus: the Focus button and the View dropdown both focus it. Setting the Focus node on every click would put it in the URL, which has two costs: each click refetches and re-renders the Overview, and (the Focus node being a navigation key) each click adds a history entry, so Back would step through every node clicked instead of through views. If ever wanted, the click should replace the current history entry rather than push, and skip the refetch.
