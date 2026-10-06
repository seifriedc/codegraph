"""Hierarchy view endpoint: /api/hierarchy/{id}?mode=type|declaration.

Wraps Graph.type_hierarchy / Graph.declaration_hierarchy and returns the shared graph
response shape. Edges keep their stored direction: type mode is child -> parent
(`inherits`), declaration mode is container -> member (`contains`/`defines`). The UI
lays out the declaration mode top to bottom as-is and flips type mode (parent on top).
"""
from __future__ import annotations

from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph
from codegraph.vis.focus import DEFAULT_LIMIT, MAX_LIMIT, shape_node
from codegraph.vis.models import NeighborhoodResponse, VisEdge

EDGE_KINDS = {"type": ["inherits"], "declaration": ["contains", "defines"]}


def hierarchy_members(g: Graph, focus_id: str, mode: str) -> list[dict]:
    """The nodes of the hierarchy around `focus_id` (the focus may or may not be included)."""
    if mode == "type":
        h = g.type_hierarchy(focus_id)
        return h["ancestors"] + h["descendants"]
    return g.declaration_hierarchy(focus_id)


def register(app: FastAPI, get_graph: Callable, rel: Callable[[str | None], str | None]) -> None:
    @app.get("/api/hierarchy/{node_id:path}", response_model=NeighborhoodResponse)
    def hierarchy(
        node_id: str,
        mode: Literal["type", "declaration"],
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
        g: Graph = Depends(get_graph),
    ) -> dict:
        focus = g.resolve_node(node_id)
        if focus is None:
            raise HTTPException(404, f"node not found: {node_id}")
        members = {n["id"]: n for n in hierarchy_members(g, focus["id"], mode)}
        members.pop(focus["id"], None)
        rest = sorted(members.values(), key=lambda n: (n["qualified_name"] or n["name"], n["id"]))
        total = len(rest) + 1
        nodes = [focus] + rest[: limit - 1]
        edges = g.edges_among([n["id"] for n in nodes], EDGE_KINDS[mode])
        return {
            "focus": focus["id"],
            "nodes": [shape_node(n, rel) for n in nodes],
            "edges": [VisEdge(**{k: e[k] for k in ("id", "kind", "source_id", "target_id")}) for e in edges],
            "truncated": total > len(nodes),
            "total": total,
        }
