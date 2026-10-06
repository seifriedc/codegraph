"""Shared shaping for the vis endpoints: caps, CSV parsing, path display and response models.

Every endpoint module (focus, expand, hierarchy, overview, search) imports from here and
never from another endpoint module.
"""
from __future__ import annotations

from typing import Callable

from codegraph.vis.models import OverviewNode, VisEdge, VisNode

Rel = Callable[[str | None], str | None]

# Server-side caps (the UI mirrors them in static/scale.js).
DEFAULT_LIMIT = 150          # nodes returned by a graph view (also Overview members)
MAX_LIMIT = 500
DEFAULT_PER_NODE_CAP = 15    # neighbors followed per node, edge kind and direction
MAX_PER_NODE_CAP = 100
MAX_DEPTH = 10
MAX_EXPANDED = 50            # expanded Group ids accepted by the Overview (the URL keeps the same cap)
MAX_SEARCH_RESULTS = 20

# Display paths of these kinds are file-system paths and are shown relative to the common root.
_PATH_KINDS = ("file", "directory")


def csv_list(value: str | None) -> list[str] | None:
    """'a,b,,c' -> ['a', 'b', 'c']; None when absent or empty."""
    items = [v for v in (value or "").split(",") if v]
    return items or None


def display_qualified_name(kind: str, qualified_name: str | None, rel: Rel) -> str | None:
    """A file or directory's qualified name is its path, so it is shown relative; others as stored."""
    return rel(qualified_name) if kind in _PATH_KINDS else qualified_name


def shape_node(n: dict, rel: Rel) -> VisNode:
    return VisNode(
        id=n["id"], kind=n["kind"], name=n["name"],
        qualified_name=display_qualified_name(n["kind"], n["qualified_name"], rel),
        path=rel(n["file_path"]),
        line_start=n["line_start"], line_end=n["line_end"], language=n["language"],
        depth=n.get("depth"),
        external=n["file_path"] is None and n["kind"] != "file",
    )


def shape_edge(e: dict) -> VisEdge:
    return VisEdge(id=e["id"], kind=e["kind"], source_id=e["source_id"], target_id=e["target_id"])


def shape_group(grp: dict, rel: Rel) -> OverviewNode:
    """An Overview Group (a derived directory or external Group, or a file/package node)."""
    return OverviewNode(
        id=grp["id"], kind=grp["kind"], name=grp["name"],
        qualified_name=display_qualified_name(grp["kind"], grp["qualified_name"], rel),
        path=rel(grp["file_path"]), line_start=None, line_end=None, language=None,
        external=grp["kind"] == "external",
        group=True, parent=grp["parent"], expanded=grp["expanded"],
        member_count=grp["member_count"], node_id=grp["node_id"],
    )


def shape_member(m: dict, rel: Rel) -> OverviewNode:
    """A member node inside an expanded Overview Group."""
    return OverviewNode(**shape_node(m, rel).model_dump(), group=False, parent=m["parent"],
                        expanded=False, member_count=0, node_id=m["id"])
