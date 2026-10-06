"""Stub node expansion endpoint: /api/expand/{id} pages in a node's hidden neighbors."""
from __future__ import annotations

from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph
from codegraph.vis.focus import DEFAULT_PER_NODE_CAP, MAX_PER_NODE_CAP, shape_node
from codegraph.vis.models import ExpandResponse, VisEdge, VisStub


def register(app: FastAPI, get_graph: Callable, rel: Callable[[str | None], str | None]) -> None:
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
            stub = VisStub(id=f"stub:{owner['id']}:{direction}:{kind}", owner=owner["id"],
                           direction=direction, kind=kind, hidden=page["hidden"], offset=shown)
        return {
            "owner": owner["id"],
            "nodes": [shape_node(n, rel) for n in page["nodes"]],
            "edges": [VisEdge(**{k: e[k] for k in ("id", "kind", "source_id", "target_id")}) for e in page["edges"]],
            "stub": stub,
            "total": page["total"],
        }
