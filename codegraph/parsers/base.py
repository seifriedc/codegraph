from __future__ import annotations
from pathlib import Path
from tree_sitter import Node as TSNode

from codegraph.models import Node, Edge, stable_id, random_id


def make_file_node(path: Path, language: str) -> Node:
    fp = str(path)
    return Node(
        id=stable_id(f"file:{fp}"),
        kind="file",
        name=path.name,
        qualified_name=fp,
        file_path=fp,
        line_start=1,
        language=language,
    )


def node_text(node: TSNode, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()


def contains_edge(parent: Node, child: Node, file_path: str, ts_node: TSNode) -> Edge:
    return Edge(
        kind="contains",
        source_id=parent.id,
        target_id=child.id,
        file_path=file_path,
        line=ts_node.start_point[0] + 1,
        col=ts_node.start_point[1],
    )


def imports_edge(source: Node, target: Node, file_path: str, ts_node: TSNode) -> Edge:
    return Edge(
        kind="imports",
        source_id=source.id,
        target_id=target.id,
        file_path=file_path,
        line=ts_node.start_point[0] + 1,
        col=ts_node.start_point[1],
    )


def calls_edge(caller: Node, callee_id: str, file_path: str, ts_node: TSNode) -> Edge:
    return Edge(
        kind="calls",
        source_id=caller.id,
        target_id=callee_id,
        file_path=file_path,
        line=ts_node.start_point[0] + 1,
        col=ts_node.start_point[1],
    )


def inherits_edge(child: Node, parent_id: str, file_path: str, ts_node: TSNode) -> Edge:
    return Edge(
        kind="inherits",
        source_id=child.id,
        target_id=parent_id,
        file_path=file_path,
        line=ts_node.start_point[0] + 1,
        col=ts_node.start_point[1],
    )


def external_node(qualified_name: str, language: str, kind: str = "module") -> Node:
    """Placeholder node for an external/unresolved reference (e.g. a with'd Ada package)."""
    return Node(
        id=stable_id(f"{kind}:{language}:{qualified_name}"),
        kind=kind,
        name=qualified_name.split(".")[-1],
        qualified_name=qualified_name,
        language=language,
    )
