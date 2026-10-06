"""Pydantic models: the JSON contract between the vis API and the UI."""
from __future__ import annotations

from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_nodes: int
    total_edges: int
    total_files: int
    nodes_by_language: dict[str, int]
    nodes_by_kind: dict[str, int]
    edges_by_kind: dict[str, int]


class VisNode(BaseModel):
    id: str
    kind: str
    name: str
    qualified_name: str | None
    path: str | None  # relative to the common ancestor of indexed files
    line_start: int | None
    line_end: int | None
    language: str | None
    depth: int | None = None  # BFS distance from the Focus node (neighborhood responses)
    external: bool  # External placeholder: referenced but not indexed


class VisEdge(BaseModel):
    id: str
    kind: str
    source_id: str
    target_id: str


class VisStub(BaseModel):
    """Stub node: stands for `hidden` neighbors of `owner` (one edge kind and direction).

    `offset` is how many of that group are already shown; pass it to /api/expand to page in more.
    """
    id: str
    owner: str
    direction: str  # "in" | "out"
    kind: str  # edge kind
    hidden: int
    offset: int


class NeighborhoodResponse(BaseModel):
    """Shared graph-response shape: nodes, edges, truncated, total (plus the focus id)."""
    focus: str
    nodes: list[VisNode]
    edges: list[VisEdge]
    stubs: list[VisStub] = []
    truncated: bool
    total: int
    # Untruncated node count per BFS ring ({"1": n, ...}); only set in impact/dependencies mode.
    ring_counts: dict[int, int] | None = None


class OverviewNode(VisNode):
    """A Group (group=True; id may be derived, e.g. a directory) or a member of an expanded Group."""
    group: bool
    parent: str | None  # id of the enclosing expanded Group (Cytoscape compound parent)
    expanded: bool
    member_count: int  # nodes inside the Group, recursively (0 for members)
    node_id: str | None  # real node to focus on / fetch details for; None for derived Groups


class OverviewEdge(BaseModel):
    """Aggregate edge: derived, one per directed pair of visible items."""
    id: str
    source_id: str
    target_id: str
    kinds: dict[str, int]  # per-kind counts
    count: int


class OverviewResponse(BaseModel):
    group_by: str
    kinds: list[str]  # edge kinds counted in this response
    available_kinds: list[str]  # every aggregatable kind in the graph (never `contains`)
    nodes: list[OverviewNode]
    edges: list[OverviewEdge]
    truncated: bool
    total: int


class NodeDetail(VisNode):
    defining_files: list[str]
    # distinct neighbor nodes per edge kind: {"in": {kind: n}, "out": {kind: n}}
    neighbor_counts: dict[str, dict[str, int]]


class ExpandResponse(BaseModel):
    """One page of a Stub node's hidden neighbors; `stub` is the continuation, null on the last page."""
    owner: str
    nodes: list[VisNode]  # depth is 1 relative to the owner
    edges: list[VisEdge]  # edges between the owner and the page
    stub: VisStub | None
    total: int


class SearchHit(VisNode):
    more_paths: int  # further files that also define this node (the "+N more" in result rows)


class SearchResponse(BaseModel):
    """Shared response shape: nodes, truncated, total."""
    nodes: list[SearchHit]
    truncated: bool
    total: int
