"""Focus view endpoints: /api/neighborhood/{id} and /api/node/{id}."""

from __future__ import annotations

from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph
from codegraph.vis.models import NeighborhoodResponse, NodeDetail
from codegraph.vis.shape import (
    DEFAULT_LIMIT,
    DEFAULT_PER_NODE_CAP,
    MAX_DEPTH,
    MAX_LIMIT,
    MAX_PER_NODE_CAP,
    Rel,
    csv_list,
    shape_edge,
    shape_node,
)


def register(app: FastAPI, get_graph: Callable, rel: Rel) -> None:
    @app.get("/api/neighborhood/{node_id:path}", response_model=NeighborhoodResponse)
    def neighborhood(
        node_id: str,
        direction: Literal["in", "out", "both"] = "both",
        depth: int = Query(1, ge=0, le=MAX_DEPTH),
        kinds: str | None = Query(
            None, description="comma-separated edge kinds (neighborhood mode)"
        ),
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
        per_node_cap: int = Query(DEFAULT_PER_NODE_CAP, ge=1, le=MAX_PER_NODE_CAP),
        mode: Literal["neighborhood", "impact", "dependencies", "both"] | None = Query(
            None,
            description="neighborhood (default): all edge kinds, honouring direction and kinds. "
            "impact / dependencies / both: the Impact set, the Dependencies or their "
            "union; these ignore direction and kinds",
        ),
        g: Graph = Depends(get_graph),
    ) -> dict:
        focus = g.resolve_node(node_id)
        if focus is None:
            raise HTTPException(404, f"node not found: {node_id}")
        if mode in ("impact", "dependencies", "both"):
            r = g.reach(focus["id"], mode=mode, depth=depth, limit=limit, per_node_cap=per_node_cap)
        else:
            r = g.neighborhood(
                focus["id"],
                direction=direction,
                depth=depth,
                edge_kinds=csv_list(kinds),
                limit=limit,
                per_node_cap=per_node_cap,
            )
        return {
            "focus": focus["id"],
            "ring_counts": r.get("ring_counts"),
            "nodes": [shape_node(n, rel) for n in r["nodes"]],
            "edges": [shape_edge(e) for e in r["edges"]],
            "stubs": r["stubs"],
            "truncated": r["truncated"],
            "total": r["total"],
        }

    @app.get("/api/node/{node_id:path}", response_model=NodeDetail)
    def node_detail(node_id: str, g: Graph = Depends(get_graph)) -> dict:
        n = g.resolve_node(node_id)
        if n is None:
            raise HTTPException(404, f"node not found: {node_id}")
        return {
            **shape_node(n, rel).model_dump(),
            "defining_files": [rel(p) for p in g.defining_files(n["id"])],
            "neighbor_counts": g.neighbor_counts(n["id"]),
        }
