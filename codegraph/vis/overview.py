"""Overview endpoint: /api/overview (Groups and derived Aggregate edges).

Stateless: the client sends the ids of the Groups it has expanded (ids come from the
previous response). `group_by` is validated by `Graph.overview`, so a new grouping
strategy there needs no change here.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, Query

from codegraph.query import Graph
from codegraph.vis.focus import shape_node
from codegraph.vis.models import OverviewEdge, OverviewNode, OverviewResponse

# calls are unreadable at overview scale (ADR 0003); off unless the client asks for them
OFF_BY_DEFAULT = {"calls"}


def register(app: FastAPI, get_graph: Callable, rel: Callable[[str | None], str | None]) -> None:
    @app.get("/api/overview", response_model=OverviewResponse)
    def overview(
        group_by: str = "directory",
        expanded: list[str] = Query(default=[], description="ids of expanded Groups"),
        kinds: str | None = Query(None, description="comma-separated edge kinds; default: all but calls"),
        externals: bool = Query(False, description="show external placeholders as one `external` Group"),
        g: Graph = Depends(get_graph),
    ) -> dict:
        available = [k for k in g.edge_kinds() if k != "contains"]
        # omitted = default set; present but empty = explicitly no kinds
        active = ([k for k in kinds.split(",") if k] if kinds is not None
                  else [k for k in available if k not in OFF_BY_DEFAULT])
        try:
            r = g.overview(group_by=group_by, expanded=expanded, kinds=active, externals=externals)
        except ValueError as e:
            raise HTTPException(422, str(e))

        nodes = [
            OverviewNode(
                id=grp["id"], kind=grp["kind"], name=grp["name"],
                qualified_name=rel(grp["qualified_name"]) if grp["kind"] in ("directory", "file") else grp["qualified_name"],
                path=rel(grp["file_path"]), line_start=None, line_end=None, language=None,
                external=grp["kind"] == "external",
                group=True, parent=grp["parent"], expanded=grp["expanded"],
                member_count=grp["member_count"], node_id=grp["node_id"],
            )
            for grp in r["groups"]
        ] + [
            OverviewNode(**shape_node(m, rel).model_dump(), group=False, parent=m["parent"],
                         expanded=False, member_count=0, node_id=m["id"])
            for m in r["nodes"]
        ]
        return {
            "group_by": group_by, "kinds": active, "available_kinds": available,
            "nodes": nodes, "edges": [OverviewEdge(**e) for e in r["edges"]],
            "truncated": r["truncated"], "total": r["total"],
        }
