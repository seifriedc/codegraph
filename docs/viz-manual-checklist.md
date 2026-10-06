# Manual checklist: graph visualization

Items for the final docs ticket. Each ticket appends its own section.

## Visual encoding, legend and kind filters (ticket 23)

Index the C++ fixtures, run `codegraph serve`, open `#focus=Shape`.

- [ ] Each node kind shows a distinct shape and tint; the graph is still readable in a greyscale screenshot.
- [ ] Each node has a small round language badge at its top-right corner (A / + / C / P, grey letter for other languages); nodes without a language have none.
- [ ] External placeholder nodes have a dashed outline.
- [ ] Edges: calls solid with filled triangle; inherits solid with hollow triangle; imports dashed; references thin dotted grey; instantiates with diamond head; contains with a hollow diamond at the source. Hues differ per kind.
- [ ] Labels keep the same on-screen size while zooming in and out; long names end in an ellipsis.
- [ ] Zoomed out below ~0.6, only the Focus node is labelled; hovering a node labels it and its neighbours and highlights them.
- [ ] Labels have a white backing and edges pass beneath them (no edge/label overlap).
- [ ] Left-panel legend lists every node and edge kind with counts for the current view; unchecking a node kind hides those nodes and their edges at once (the Focus node never hides).
- [ ] Unchecking an edge kind hides it and refetches with the `kinds` param (check the network tab).
- [ ] The on-canvas mini legend (bottom-left) shows only kinds that are visible and present, and collapses/expands.
- [ ] Layout and refocus still behave (positions stable) with filters active.

## Overview with Directory grouping (ticket 24)

Index `tests/fixtures`, run `codegraph serve`, open the bare URL (no hash). Not verified in a browser by the implementer.

- [ ] The overview is the landing view; the search box has focus; depth/mode/view controls and the legend are hidden.
- [ ] Top level shows `ada`, `c`, `cpp` Groups (labelled with sizes) and one external Group; edges have arrowheads and log-scaled thickness.
- [ ] `calls` is unchecked in the kind filter; ticking it adds edges, and unticking an edge kind re-aggregates (thickness changes, empty pairs disappear).
- [ ] Hovering an edge shows the source and target and per-kind counts (e.g. `calls: 2, references: 1`).
- [ ] Clicking a collapsed Group expands it in place (a box around its files, fcose re-settles, other Groups stay put); clicking an expanded box collapses it. Back/forward and reload keep the expansion (`expanded=` in the hash).
- [ ] Expanding a file shows its functions/classes inside it; selecting any node with a real id enables Focus, which opens `#focus=<id>`; the Overview button returns.
- [ ] Choosing a search result from the overview switches to the focus view.
