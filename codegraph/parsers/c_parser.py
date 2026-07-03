from __future__ import annotations
from pathlib import Path

from tree_sitter import Language, Parser, Node as TSNode
import tree_sitter_c

from codegraph.models import Node, Edge, stable_id, random_id
from codegraph.parsers.base import (
    make_file_node, node_text, contains_edge,
    imports_edge, calls_edge, references_edge, external_node,
)

_LANGUAGE = Language(tree_sitter_c.language())
_PARSER = Parser(_LANGUAGE)


def parse(path: Path) -> tuple[list[Node], list[Edge]]:
    source = path.read_bytes()
    tree = _PARSER.parse(source)
    fp = str(path)

    nodes: list[Node] = []
    edges: list[Edge] = []

    file_node = make_file_node(path, "c")
    nodes.append(file_node)

    _walk(tree.root_node, file_node, fp, nodes, edges, source)
    return nodes, edges


def _function_name(ts_node: TSNode, source: bytes) -> str | None:
    declarator = ts_node.child_by_field_name("declarator")
    if declarator is None:
        return None
    return _declarator_name(declarator, source)


def _declarator_name(ts_node: TSNode, source: bytes) -> str | None:
    if ts_node.type in ("identifier", "field_identifier"):
        return node_text(ts_node, source)
    if ts_node.type == "function_declarator":
        inner = ts_node.child_by_field_name("declarator")
        if inner:
            return _declarator_name(inner, source)
    if ts_node.type == "pointer_declarator":
        inner = ts_node.child_by_field_name("declarator")
        if inner:
            return _declarator_name(inner, source)
    for child in ts_node.named_children:
        name = _declarator_name(child, source)
        if name:
            return name
    return None


def _walk(
    ts_node: TSNode,
    parent: Node,
    file_path: str,
    nodes: list[Node],
    edges: list[Edge],
    source: bytes,
) -> None:
    current = parent

    if ts_node.type == "function_definition":
        name = _function_name(ts_node, source)
        if name:
            n = Node(
                id=stable_id(f"function:c:{name}"),
                kind="function",
                name=name,
                qualified_name=name,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="c",
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
            current = n

    elif ts_node.type == "struct_specifier":
        name_node = ts_node.child_by_field_name("name")
        if name_node:
            name = node_text(name_node, source)
            n = Node(
                id=stable_id(f"type:c:{name}"),
                kind="type",
                name=name,
                qualified_name=name,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="c",
                metadata={"struct": True},
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
        return  # don't recurse into struct body

    elif ts_node.type == "preproc_include":
        _handle_include(ts_node, current, file_path, nodes, edges, source)
        return

    elif ts_node.type == "call_expression":
        _handle_call(ts_node, current, file_path, nodes, edges, source)
        return

    elif ts_node.type == "type_identifier":
        # User-defined type reference (primitives are primitive_type, not type_identifier)
        type_name = node_text(ts_node, source)
        type_id = stable_id(f"type:c:{type_name}")
        ext = external_node(type_name, "c", "type")
        nodes.append(ext)
        edges.append(references_edge(current.id, type_id, file_path, ts_node))
        return

    for child in ts_node.named_children:
        _walk(child, current, file_path, nodes, edges, source)


def _handle_include(
    ts_node: TSNode, parent: Node, file_path: str,
    nodes: list[Node], edges: list[Edge], source: bytes,
) -> None:
    path_node = ts_node.child_by_field_name("path")
    if path_node is None:
        path_node = ts_node.named_children[0] if ts_node.named_children else None
    if path_node:
        raw = node_text(path_node, source).strip("<>\"")
        ext = external_node(raw, "c", "module")
        nodes.append(ext)
        edges.append(imports_edge(parent, ext, file_path, ts_node))


def _handle_call(
    ts_node: TSNode, caller: Node, file_path: str,
    nodes: list[Node], edges: list[Edge], source: bytes,
) -> None:
    fn_node = ts_node.child_by_field_name("function")
    if fn_node is None:
        return
    name = node_text(fn_node, source)
    callee_id = stable_id(f"function:c:{name}")
    ext = external_node(name, "c", "function")
    nodes.append(ext)
    edges.append(calls_edge(caller, callee_id, file_path, ts_node))
