"""Overview endpoint: /api/overview (Groups and derived Aggregate edges).

Stateless: the client sends the ids of the Groups it has expanded (ids come from the
previous response; directory ids are relative to the indexed root, never absolute paths).
`group_by` is validated by `Graph.overview`, so a new grouping strategy there needs no
change here. Work is bounded: at most MAX_EXPANDED expanded ids are accepted and at most
`limit` member nodes are returned.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph
from codegraph.vis.models import OverviewEdge, OverviewResponse
from codegraph.vis.shape import DEFAULT_LIMIT, MAX_EXPANDED, MAX_LIMIT, Rel, csv_list, shape_group, shape_member

# calls are unreadable at overview scale (ADR 0003); off unless the client asks for them
OFF_BY_DEFAULT = {"calls"}


def register(app: FastAPI, get_graph: Callable, rel: Rel) -> None:
    @app.get("/api/overview", response_model=OverviewResponse)
    def overview(
        group_by: str = "directory",
        expanded: list[str] = Query(default=[], max_length=MAX_EXPANDED, description="ids of expanded Groups"),
        kinds: str | None = Query(None, description="comma-separated edge kinds; default: all but calls"),
        externals: bool = Query(False, description="show external placeholders as one `external` Group"),
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="cap on member nodes of expanded Groups"),
        g: Graph = Depends(get_graph),
    ) -> dict:
        available = [k for k in g.edge_kinds() if k != "contains"]
        # omitted = default set; present but empty = explicitly no kinds
        active = ((csv_list(kinds) or []) if kinds is not None
                  else [k for k in available if k not in OFF_BY_DEFAULT])
        try:
            r = g.overview(group_by=group_by, expanded=expanded, kinds=active, externals=externals,
                           member_limit=limit)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {
            "group_by": group_by, "kinds": active, "available_kinds": available,
            "nodes": [shape_group(grp, rel) for grp in r["groups"]] + [shape_member(m, rel) for m in r["nodes"]],
            "edges": [OverviewEdge(**e) for e in r["edges"]],
            "truncated": r["truncated"], "total": r["total"],
        }
