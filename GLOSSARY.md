# codegraph

A polyglot source code knowledge graph: indexes source files into nodes and edges for navigation, impact analysis and visualization.

## Language

**Package**:
A named language-level container of declarations, materialized as a node at index time (e.g. an Ada package). Packages can nest via `contains` edges.
_Avoid_: Module (reserved for external include/import placeholders), namespace (a future C++ source of Packages)

**Group**:
Any node the overview can collapse its members into: a Package, a file, or a directory.
_Avoid_: Cluster, container

**Overview**:
The architecture-level view of the graph showing Groups and aggregated edges between them, as opposed to a focus view around one node.
_Avoid_: Map, dashboard

**Aggregate edge**:
A single derived edge between two Groups summarizing all member-level edges between them, with per-kind counts. Never stored.
_Avoid_: Rollup edge, package edge

**Focus node**:
The node an exploration view is centred on; neighbourhoods expand outward from it.
_Avoid_: Root, selected node

**External placeholder**:
A node for something referenced but not indexed (e.g. `math.h`, `Ada.Numerics`).
_Avoid_: Stub, unresolved node

**Neighborhood**:
The set of nodes and edges within a given depth of a Focus node, optionally restricted by edge kind and direction. Impact analysis is a Neighborhood over `calls`.
_Avoid_: Subgraph, ego graph

**Stub node**:
A placeholder in a view standing for hidden neighbours of a node (e.g. "+185 callers"); clicking it reveals more.
_Avoid_: Overflow node, more-node

**Impact set**:
The Neighborhood over incoming `calls`, `references`, `instantiates` and `inherits` (descendants) edges: what is affected if the Focus node changes.
_Avoid_: Blast radius, callers (callers are only the `calls` subset)

**Dependencies**:
The Neighborhood over the outgoing equivalents of the Impact set's edges: what the Focus node relies on.
_Avoid_: Callees
