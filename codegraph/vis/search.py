"""Search endpoint: /api/search (type-ahead over name, qualified name and, for path-like queries, path)."""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, FastAPI, Query

from codegraph.query import Graph
from codegraph.vis.focus import shape_node
from codegraph.vis.models import SearchHit, SearchResponse

MAX_RESULTS = 20


def _csv(value: str | None) -> list[str] | None:
    items = [v for v in (value or "").split(",") if v]
    return items or None


def register(app: FastAPI, get_graph: Callable, rel: Callable[[str | None], str | None]) -> None:
    @app.get("/api/search", response_model=SearchResponse)
    def search(
        q: str = Query(..., min_length=1, description="substring; path is matched only if it contains / or ."),
        kinds: str | None = Query(None, description="comma-separated node kinds"),
        languages: str | None = Query(None, description="comma-separated languages"),
        g: Graph = Depends(get_graph),
    ) -> dict:
        r = g.search(q, kinds=_csv(kinds), languages=_csv(languages), limit=MAX_RESULTS)
        return {
            "nodes": [
                SearchHit(**shape_node(n, rel).model_dump(), more_paths=max(n["file_count"] - 1, 0))
                for n in r["nodes"]
            ],
            "total": r["total"],
            "truncated": r["truncated"],
        }
