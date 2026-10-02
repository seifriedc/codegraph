# Research: live physics layout options (#9)

Facts only, no decision. Builds on `research/graph-rendering-libs` (#2: Cytoscape.js 3.34.3, Sigma 3.0.3, d3-force 3.0.0, elkjs, dagre).
Sizes: jsDelivr dist files, raw / gzip -9, measured 2026-10-02. Versions/licenses: npm registry `latest`.

## Comparison

| Option | Ver / license | Size raw / gz (+ deps) | Continuous sim | Incremental add/remove | Compound / collapse | Labels | Pin node |
|---|---|---|---|---|---|---|---|
| cytoscape-cola (WebCola) | 2.5.1 / MIT | 22 KB / 6 KB + webcola 80 KB / 23 KB | Runs until `convergenceThreshold` (alpha) or `maxSimulationTime` (default 4000 ms); no documented "forever" option | Not documented; `randomize:false`, `centerGraph:false` start from current positions | README: "supports noncompound and compound graphs well"; `flow` (DAG axis) + `alignment`/`gapInequalities` constraints | `nodeDimensionsIncludeLabels`, `avoidOverlap` (bounding boxes) | Via cytoscape `locked` (not cola-specific doc) |
| cytoscape-fcose | 2.2.0 / MIT | 57 KB / 13 KB + cose-base 119 KB / 22 KB + layout-base 148 KB / 34 KB | One-shot layout with animation, not continuous | "Incremental layout" options (`randomize:false`, `quality`, `initialEnergyOnIncremental` 0.3); constraints "can also be added incrementally on a given layout" | Full compound support (paper title: "Fast Compound Graph Layout Algorithm with Constraint Support") | `nodeDimensionsIncludeLabels` valid only in `quality:"proof"` | `fixedNodeConstraint` (exact positions), alignment, relative placement |
| cytoscape-d3-force | 1.1.4 / MIT | 18 KB / 5 KB + d3-force ^2 (8 KB / 3 KB) | `infinite: true` = "forces-all-the-time mode"; alpha/alphaMin/alphaDecay/alphaTarget exposed | Not documented | None (d3-force has no compound concept) | None | `fixedAfterDragging` option |
| d3-force | 3.0.0 / ISC | 8 KB / 3 KB (+ d3-timer/dispatch/quadtree) | Yes: internal timer; `alphaTarget` + `restart()` to reheat | `simulation.nodes([...])` re-set; `restart()` | None | None (no renderer) | `node.fx`/`node.fy` (reset each tick, velocity zeroed); unfix with null |
| force-graph (vasturiano) | 1.52.0 / MIT | 173 KB / 56 KB bundled; npm deps incl. d3-force-3d, d3-zoom, d3-drag, kapsule, lodash-es | Yes: d3 engine; `cooldownTicks` (default Infinity), `cooldownTime` (default 15000 ms), `d3ReheatSimulation()`, `autoPauseRedraw` | `graphData()` "can also be used to apply incremental updates" (official `dynamic` example) | None built in; official "expandable-nodes" example (click expand/collapse); `dagMode` (td/bu/lr/rl/radial) for DAG only, "without cycles" | Canvas; `nodeLabel` is hover label; custom `nodeCanvasObject` for own drawing; `onZoom({k,x,y})` gives zoom for scaling; link width stays constant across zoom | Official "fix-dragged-nodes" example (fx/fy via d3) |
| vis-network | 10.1.2 / Apache-2.0 OR MIT | standalone UMD 652 KB / 155 KB, no deps | Yes: solvers `barnesHut` (default), `forceAtlas2Based`, `repulsion`, `hierarchicalRepulsion`; `stabilization` on load; physics restarts on node drag; start/stop methods | Not verified here (docs read: physics restarts when a node is dragged) | Clustering: `cluster`, `clusterByConnection`, `clusterByHubsize`, `clusterOutliers`, `openCluster`; clusters nest; replaces members with a cluster node (not a drawn box); cannot link edges to a cluster | `avoidOverlap` per solver (not for `repulsion`); Canvas | Node `fixed`/ physics-off per node (vis docs); not verified here |
| Cytoscape.js core | 3.34.3 / MIT | 435 KB / 136 KB | n/a (layouts are extensions) | `cy.add()`, `cy.batch()` | Core compound nodes (`parent`) | per #2 | `locked` |
| cytoscape-expand-collapse | 4.1.1 / MIT | 31 KB / 9 KB | n/a | n/a | Expand/collapse compound nodes + meta-edges; `layoutBy` re-layout after toggle (suggests cose-bilkent `randomize:false` to preserve mental map). README: "no longer being maintained" | n/a | n/a |

Not measured: graphology-layout-forceatlas2 0.10.1 (MIT; dist path not found on jsDelivr), d3-force-3d 3.0.6 (MIT; 11 KB / 4 KB, 2D+3D fork used by force-graph).

## Cross-cutting facts

- No surveyed option provides all of: continuous physics + incremental updates + drawn collapsible compound boxes + layered mode in one library.
- Layered/hierarchy: elkjs and dagre (from #2) are layout-only; force-graph `dagMode` is DAG-only; vis-network has a `hierarchical` layout that auto-selects the `hierarchicalRepulsion` solver; cola has `flow` constraint.
- Compound force layouts: fCoSE (incremental, constraints, 2022 TVCG paper; last release per #2 was 2023) and cola. Neither README documents a continuous/"alive" mode.
- Continuous mode is native only in d3-force (and wrappers force-graph, cytoscape-d3-force `infinite`) and vis-network physics.
- Label overlap: no surveyed library documents label-collision avoidance. Only node-box `avoidOverlap` (cola, vis-network) and `nodeDimensionsIncludeLabels` (cola, fcose "proof") account for label size. Zoom-scaled labels: force-graph exposes zoom via `onZoom`; Cytoscape handles zoom natively (canvas renderer, per #2).
- Sizes for vendoring: d3-force 3 KB gz is smallest; cola + webcola ~29 KB gz; fcose + deps ~70 KB gz; force-graph 56 KB gz; vis-network 155 KB gz (all excluding Cytoscape core 136 KB gz where an extension).

## Unverified / open

- Whether cytoscape-cola can run indefinitely (no option documented) or accept added/removed nodes without restart.
- Whether vis-network pinning/fixed semantics and cluster behavior match the "box" model; clusters are node-replacement, not enclosing boxes.
- Performance at a few thousand nodes for any continuous option (no first-party benchmarks read).
- d3-force-based compound containment (e.g., custom cluster/box forces) is not a first-party feature.

## Sources

- https://github.com/cytoscape/cytoscape.js-cola (README)
- https://github.com/iVis-at-Bilkent/cytoscape.js-fcose (README)
- https://github.com/shichuanpo/cytoscape.js-d3-force (README)
- https://d3js.org/d3-force/simulation
- https://github.com/vasturiano/force-graph (README, examples)
- https://github.com/visjs/vis-network (docs/network/physics.html, docs/network/index.html)
- https://github.com/iVis-at-Bilkent/cytoscape.js-expand-collapse (README)
- npm registry package metadata; jsDelivr dist files for sizes
