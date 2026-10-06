# Cytoscape.js renderer with a d3-force live layout and per-view layout engines

The UI renders with Cytoscape.js (canvas). Focus views (neighborhood, impact) use a d3-force simulation that we drive ourselves, writing positions into Cytoscape each tick, so nodes float and repel Neo4j-style without manual dragging. Hierarchy views use dagre (layered, top-to-bottom). Overview views use fcose (compound, collapsible groups). All libraries are vendored into the prebuilt static bundle; no node is needed at install time.

## Terms

- **Continuous**: the layout is a running physics simulation, not a one-shot computation. Nodes keep moving, repel each other and settle on their own, and nodes or edges can be added or removed while it runs without recomputing the whole layout. This is what gives the Neo4j-style "alive" feel.
- **Compound**: the graph has nested nodes, where a parent node contains children and is drawn as a box around them (e.g. a package or directory containing its functions). A compound layout must keep children inside their parent and still route edges across box boundaries. This is what collapsible Groups in the overview need.

## Why a custom physics loop

No surveyed library is both continuous and compound. cytoscape-cola's infinite mode was prototyped and rejected: dragging any node also moved the pinned focus node, and it performed worse than d3-force on a ~700-node graph. d3-force is small, continuous, supports pinned nodes and incremental add/remove, and keeps positions stable across refocus.

## Consequences

- We own the simulation lifecycle: it must cool and then sleep (stop ticking) within a bounded time, wake on interaction ("reheat"), and keep the focus node pinned while other nodes remain draggable.
- Collision radius is tuned for labels, since no library handles label overlap.
- Overview readability with `calls` enabled was poor in fcose, so overview defaults to `calls` off (see the scale and encoding decisions).
- Rejected: Sigma.js (no compound or layered layout), vis-network (no compound), Cytoscape WebGL (preview API).
