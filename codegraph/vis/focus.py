"""Focus view endpoints: /api/neighborhood/{id} and /api/node/{id}."""
from __future__ import annotations

from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph
from codegraph.vis.models import NeighborhoodResponse, NodeDetail, VisEdge, VisNode, VisStub

DEFAULT_LIMIT = 150
MAX_LIMIT = 500
DEFAULT_PER_NODE_CAP = 15
MAX_PER_NODE_CAP = 100
MAX_DEPTH = 10


def shape_node(n: dict, rel: Callable[[str | None], str | None]) -> VisNode:
    is_file = n["kind"] == "file"
    return VisNode(
        id=n["id"], kind=n["kind"], name=n["name"],
        qualified_name=rel(n["qualified_name"]) if is_file else n["qualified_name"],
        path=rel(n["file_path"]),
        line_start=n["line_start"], line_end=n["line_end"], language=n["language"],
        depth=n.get("depth"),
        external=n["file_path"] is None and not is_file,
    )


def register(app: FastAPI, get_graph: Callable, rel: Callable[[str | None], str | None]) -> None:
    @app.get("/api/neighborhood/{node_id:path}", response_model=NeighborhoodResponse)
    def neighborhood(
        node_id: str,
        direction: Literal["in", "out", "both"] = "both",
        depth: int = Query(1, ge=0, le=MAX_DEPTH),
        kinds: str | None = Query(None, description="comma-separated edge kinds"),
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
        per_node_cap: int = Query(DEFAULT_PER_NODE_CAP, ge=1, le=MAX_PER_NODE_CAP),
        g: Graph = Depends(get_graph),
    ) -> dict:
        focus = g.resolve_node(node_id)
        if focus is None:
            raise HTTPException(404, f"node not found: {node_id}")
        edge_kinds = [k for k in kinds.split(",") if k] if kinds else None
        r = g.neighborhood(focus["id"], direction=direction, depth=depth,
                           edge_kinds=edge_kinds, limit=limit, per_node_cap=per_node_cap)
        return {
            "focus": focus["id"],
            "nodes": [shape_node(n, rel) for n in r["nodes"]],
            "edges": [VisEdge(**{k: e[k] for k in ("id", "kind", "source_id", "target_id")}) for e in r["edges"]],
            "stubs": [VisStub(**st) for st in r["stubs"]],
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
            "neighbour_counts": g.neighbour_counts(n["id"]),
        }
