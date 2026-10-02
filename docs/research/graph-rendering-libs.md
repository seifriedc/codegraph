# Research: graph rendering libraries

Issue: seifriedc/codegraph#2 (map: #1). Researched 2026-10-02. Facts and trade-offs only; no decision.

Question: which browser graph render/layout lib fits expand-on-demand neighborhoods, layered/tree layouts (type/declaration hierarchies), compound nodes (package overview), a few thousand visible nodes, small prebuilt bundle, no runtime node dependency.

Method: official sites/READMEs/docs, plus package contents measured directly from the npm registry / jsDelivr (published artifacts). Doc pages were read via a summarizing fetch tool, so exact wording of quotes is as returned; items I could not confirm are marked UNVERIFIED.

## Summary table

| Lib | Role | Compound nodes | Layered/tree layout | Renderer | Min size (raw / gzip) | License |
|---|---|---|---|---|---|---|
| Cytoscape.js 3.34.3 | render + graph model + layouts | yes (core) | via extensions (dagre, elk) | Canvas; WebGL preview | 435,503 / 136,449 B | MIT |
| Sigma.js 3.0.3 (+ graphology 0.26.0) | render only | not mentioned in docs | none built in | WebGL | 187,876 / 47,196 B (+73,629 / 13,871 graphology) | MIT |
| d3-force 3.0.0 | force sim only | no | no (force only) | none (agnostic) | 8,300 / 2,991 B | ISC |
| elkjs 0.12.0 | layout only | yes (hierarchy handling) | yes (layered, mrtree) | none | 1,609,707 / 466,703 B (bundled) | EPL-2.0 OR GPL-3.0-or-later |
| dagre (@dagrejs/dagre 3.1.1) | layout only | partial/UNVERIFIED | yes (layered) | none | 48,956 / 17,063 B | MIT |

Sizes: `curl` of jsDelivr files, `dist/*.min.js` (or unminified where no min file published: fcose, elk adapter, cytoscape-dagre, expand-collapse), gzip -c default level. Measured 2026-10-02.

## Cytoscape.js

- Graph theory lib + visualization; supports "compound graphs"; "No external dependencies"; MIT. https://js.cytoscape.org/
- npm `cytoscape` 3.34.3 (published 2026-09-07), `dependencies: []`. https://registry.npmjs.org/cytoscape/latest
- Compound nodes: set `parent` in node data; parent bbox/position is inferred from descendants (no independent size); `eles.move()` reparents (parent normally immutable via `data()`). https://js.cytoscape.org/#notation/compound-nodes
- Dynamic add: `cy.add()`; `cy.batch()` coalesces style updates/redraw into one. https://js.cytoscape.org/ (Core/Collection API)
- Built-in layouts: grid, circle, concentric (plus null/preset/random/breadthfirst, cose per site; first three confirmed by fetch). Others are extensions: dagre, ELK, fCoSE, CoSE-Bilkent. https://js.cytoscape.org/
- Renderer: Canvas. A WebGL renderer is a preview since 3.31, enabled by `renderer: { name: 'canvas', webgl: true }`; "options or API ... provisional and may change". Edges limited: straight/haystack/bezier only, no dashed lines, no source/target labels, triangle solid arrows only. Blog benchmark (M1 MacBook Pro, vendor): 1200 nodes/16000 edges ~20 FPS canvas vs >100 FPS WebGL. https://blog.js.cytoscape.org/2025/01/13/webgl-preview/ . Shipped 3.34.3 bundle contains the `webgl` option and `webgl*` renderer settings (verified in https://cdn.jsdelivr.net/npm/cytoscape@3.34.3/dist/cytoscape.min.js).
- Perf options `hideEdgesOnViewport`, `textureOnViewport`, `motionBlur` exist but are described as "largely moot" after performance work. https://js.cytoscape.org/
- Extensions (all MIT, peer-dep on cytoscape):
  - cytoscape-dagre 4.0.1: dagre bundled into dist; "especially suitable for DAGs and trees"; README does not address compound nodes. https://github.com/cytoscape/cytoscape.js-dagre . 58,298 B / 20,061 gz.
  - cytoscape-elk 2.3.0: adapter; needs elkjs >=0.9.2 (separate dep); algorithms box, disco, force, layered, mrtree, random, stress; per-node options via `nodeLayoutOptions`. https://github.com/cytoscape/cytoscape.js-elk . 11,301 B / 3,729 gz (excl. elkjs).
  - cytoscape-fcose 2.2.0: force-directed with compound support, fixed/alignment/relative-placement constraints, incremental layout; deps cose-base; claims ~2x faster than CoSE (paper: Balci & Dogrusoz, IEEE TVCG 2022). https://github.com/iVis-at-Bilkent/cytoscape.js-fcose . 57,239 B / 13,404 gz. Last publish 2023-01-17.
  - cytoscape-expand-collapse 4.1.1: collapse/expand compound nodes (`collapse/expand(All|Recursively)`, edge collapsing); `layoutBy` option to relayout after; repo states it is "no longer being maintained". https://github.com/iVis-at-Bilkent/cytoscape.js-expand-collapse . 31,284 B / 8,914 gz. Last publish 2024-08-28.
- Note: expand-collapse operates on existing compound nodes (collapse/expand children), not on fetching neighborhoods from a server; on-demand neighborhood expansion would be `cy.add()` of fetched elements plus a relayout (inference from API above, not a documented feature).

## Sigma.js (+ graphology)

- WebGL renderer; "draw larger graphs faster than with Canvas or SVG"; targets "thousands of nodes and edges"; docs suggest d3 for "a few hundreds" of nodes. MIT. https://www.sigmajs.org/
- Uses graphology as the data model; layouts are not in sigma, they come from graphology (e.g. ForceAtlas2). https://www.sigmajs.org/
- sigma 3.0.3 deps: `events`, `graphology-utils` (graphology is a peer-style requirement in use). https://registry.npmjs.org/sigma/latest . graphology 0.26.0 (last publish 2025-01-26), MIT.
- graphology-layout provides circular, random, circle-pack, plus coordinate helpers; no layered/tree layout listed. https://graphology.github.io/standard-library/layout.html
- Compound/grouped nodes: not mentioned in sigma or graphology docs fetched (UNVERIFIED either way; graphology docs not exhaustively read).
- Layered/tree layouts would need an external layout (e.g. elkjs/dagre) computing positions that are assigned to graphology node attributes (inference; no first-party doc statement found).

## d3-force

- Velocity Verlet simulation; forces: center, collide, link, many-body, position; for network and hierarchical (force-directed tree) visualization; renderer-agnostic via `tick` events (Canvas/SVG/other). ISC. https://d3js.org/d3-force
- npm d3-force 3.0.0 (published 2021-06-05; registry modified 2022-06-14); deps d3-timer, d3-dispatch, d3-quadtree. https://registry.npmjs.org/d3-force/latest
- Provides positions only: no rendering, no compound nodes, no layered layout, no interaction/hit-testing; those are built by the app.

## elkjs (Eclipse Layout Kernel)

- Layout only ("compute positions for diagram elements rather than render"). Algorithms: layered, stress, mrtree, radial, force, disco, plus box/fixed/random. Layered is Sugiyama-style, suited to inherently directed graphs. https://github.com/kieler/elkjs
- Compound graphs: layered "support[s] full layout of compound graphs with cross-hierarchy edges" when enabled on the top level. `elk.hierarchyHandling = INCLUDE_CHILDREN` lays out a node and descendants in one run (needed for cross-level edges); default (unset/INHERIT at root) is `SEPARATE_CHILDREN`, one layout run per compound level. https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html , https://eclipse.dev/elk/reference/options/org-eclipse-elk-hierarchyHandling.html
- Distribution: `elk-api.js` (9,782 B), `elk-worker.min.js` (1,595,334 B, GWT-compiled from Java), `elk.bundled.js` (1,609,707 B / 466,703 gz). Web Worker supported to avoid UI freeze. https://github.com/kieler/elkjs ; sizes measured from https://cdn.jsdelivr.net/npm/elkjs@0.12.0/lib/
- npm 0.12.0 (2026-07-17); no deps; license "EPL-2.0 OR GPL-3.0-or-later". https://registry.npmjs.org/elkjs/latest
- Used by Mermaid, Cytoscape (adapter), React Flow, Sprotty, netlistsvg (per README).
- No performance benchmarks found in first-party docs for a few thousand nodes.

## dagre

- Client-side directed graph layout; "speed" for "medium sized graphs"; renderer-agnostic; options: rankdir TB/BT/LR/RL, nodesep/edgesep/ranksep, ranker network-simplex/tight-tree/longest-path. MIT. https://github.com/dagrejs/dagre/wiki
- Wiki cites Sander's "Layout of Compound Directed Graphs" and says clustering is addressed "on all phases of layout"; README does not state compound support or limits (UNVERIFIED how complete). https://github.com/dagrejs/dagre/wiki
- Two npm packages exist; `@dagrejs/dagre` is the maintained one (3.1.1, 2026-08-08; dep @dagrejs/graphlib). Wiki last edited Nov 2023; 172 open issues. https://github.com/dagrejs/dagre ; https://registry.npmjs.org/@dagrejs/dagre/latest
- No benchmark data in wiki.

## Fit against the five criteria (facts mapped, not ranked)

1. Expand-on-demand neighborhoods: Cytoscape `cy.add()` + `cy.batch()` are documented incremental APIs; fCoSE documents incremental layout (keeps existing positions; constraints); Sigma/graphology and d3-force accept dynamic data but the docs fetched do not describe incremental layout; elk/dagre are re-run layouts (no incremental mode documented).
2. Layered/tree layouts: elkjs layered/mrtree and dagre are first-party layered layouts; Cytoscape reaches them via extensions; Sigma and d3-force have none built in.
3. Compound nodes: Cytoscape core (+ fCoSE, expand-collapse, elk hierarchy); elkjs hierarchy handling; dagre unclear; Sigma/graphology not documented; d3-force no.
4. Few thousand visible nodes: Sigma (WebGL, targets thousands) and Cytoscape WebGL preview (provisional, limited edge styles) are documented as GPU paths; Cytoscape Canvas is the default and stable; d3 itself suggests Canvas/SVG rendering by the app. No first-party benchmark found at "a few thousand" for the layout libs.
5. Small prebuilt bundle, no node at runtime: all are plain browser JS available as prebuilt files via npm/CDN, so none needs node at `pip install` time if vendored into the static bundle. Size ranking (gzip): d3-force ~3 KB; dagre ~17 KB; sigma ~47 KB (+14 KB graphology); cytoscape ~136 KB (+ extensions 4-20 KB each); elkjs ~467 KB (+ 4 KB adapter if via Cytoscape).

## Trade-offs / caveats

- Cytoscape is the only single lib with core compound nodes, dynamic add, built-in non-layered layouts, and an extension path to layered layouts; cost is larger bundle and extension maintenance state (expand-collapse unmaintained; fcose last release 2023).
- Sigma is lightest WebGL path but is render-only: layouts, hierarchy/compound, and layered positions must come from elsewhere.
- elkjs is the most capable first-party layered + hierarchical layout but ~1.6 MB raw (worker is the bulk) and dual license EPL-2.0 OR GPL-3.0-or-later (check redistribution terms in a pip wheel).
- dagre is small and MIT but compound handling is unconfirmed.
- Layout libs compute positions only; interaction (pan/zoom/select) comes from the renderer.

## Open items not resolved from primary sources

- Dagre compound-node behavior and limits.
- Sigma/graphology compound-node story.
- Any first-party scale benchmarks at several thousand nodes with compound layout (elk, fcose, dagre).
- Whether a Cytoscape WebGL preview is stable enough for production (vendor says provisional).
