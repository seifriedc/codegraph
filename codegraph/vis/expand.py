"""Stub node expansion endpoint: /api/expand/{id} pages in a node's hidden neighbors."""
from __future__ import annotations

from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph, stub_id
from codegraph.vis.models import ExpandResponse, VisStub
from codegraph.vis.shape import DEFAULT_PER_NODE_CAP, MAX_PER_NODE_CAP, Rel, shape_edge, shape_node


def register(app: FastAPI, get_graph: Callable, rel: Rel) -> None:
    @app.get("/api/expand/{node_id:path}", response_model=ExpandResponse)
    def expand(
        node_id: str,
        direction: Literal["in", "out"],
        kind: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(DEFAULT_PER_NODE_CAP, ge=1, le=MAX_PER_NODE_CAP),
        g: Graph = Depends(get_graph),
    ) -> dict:
        owner = g.resolve_node(node_id)
        if owner is None:
            raise HTTPException(404, f"node not found: {node_id}")
        page = g.neighbors_page(owner["id"], direction, kind, offset=offset, limit=limit)
        shown = offset + len(page["nodes"])
        stub = None
        if page["hidden"]:
            stub = VisStub(id=stub_id(owner["id"], direction, kind), owner=owner["id"],
                           direction=direction, kind=kind, hidden=page["hidden"], offset=shown)
        return {
            "owner": owner["id"],
            "nodes": [shape_node(n, rel) for n in page["nodes"]],
            "edges": [shape_edge(e) for e in page["edges"]],
            "stub": stub,
            "total": page["total"],
        }
