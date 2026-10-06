"""Hierarchy view endpoint: /api/hierarchy/{id}?mode=type|declaration.

Wraps Graph.hierarchy and returns the shared graph response shape. Edges keep their stored
direction: type mode is child -> parent (`inherits`), declaration mode is container -> member
(`contains`/`defines`). The UI lays out the declaration mode top to bottom as-is and flips
type mode (parent on top). Over the limit the deepest ring is dropped first.
"""

from __future__ import annotations

from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph
from codegraph.vis.models import NeighborhoodResponse
from codegraph.vis.shape import DEFAULT_LIMIT, MAX_LIMIT, Rel, shape_edge, shape_node


def register(app: FastAPI, get_graph: Callable, rel: Rel) -> None:
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
        r = g.hierarchy(focus["id"], mode, limit=limit)
        return {
            "focus": focus["id"],
            "ring_counts": r["ring_counts"],
            "nodes": [shape_node(n, rel) for n in r["nodes"]],
            "edges": [shape_edge(e) for e in r["edges"]],
            "truncated": r["truncated"],
            "total": r["total"],
        }
