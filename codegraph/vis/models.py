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


class NeighborhoodResponse(BaseModel):
    """Shared graph-response shape: nodes, edges, truncated, total (plus the focus id)."""
    focus: str
    nodes: list[VisNode]
    edges: list[VisEdge]
    truncated: bool
    total: int


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
    # distinct neighbour nodes per edge kind: {"in": {kind: n}, "out": {kind: n}}
    neighbour_counts: dict[str, dict[str, int]]
