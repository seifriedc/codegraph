from __future__ import annotations
from pathlib import Path

from tree_sitter import Language, Parser, Node as TSNode
import tree_sitter_cpp

from codegraph.models import Node, Edge, stable_id, random_id
from codegraph.parsers.base import (
    make_file_node, node_text, contains_edge,
    imports_edge, calls_edge, inherits_edge, external_node,
)
from codegraph.parsers.c_parser import _function_name, _declarator_name, _handle_include, _handle_call

_LANGUAGE = Language(tree_sitter_cpp.language())
_PARSER = Parser(_LANGUAGE)


def parse(path: Path) -> tuple[list[Node], list[Edge]]:
    source = path.read_bytes()
    tree = _PARSER.parse(source)
    fp = str(path)

    nodes: list[Node] = []
    edges: list[Edge] = []

    file_node = make_file_node(path, "cpp")
    nodes.append(file_node)

    _walk(tree.root_node, file_node, fp, nodes, edges, source, class_context=None)
    return nodes, edges


def _walk(
    ts_node: TSNode,
    parent: Node,
    file_path: str,
    nodes: list[Node],
    edges: list[Edge],
    source: bytes,
    class_context: Node | None,
) -> None:
    current = parent

    if ts_node.type == "class_specifier":
        name_node = ts_node.child_by_field_name("name")
        if name_node:
            name = node_text(name_node, source)
            qname = f"{class_context.qualified_name}::{name}" if class_context else name
            n = Node(
                id=stable_id(f"class:cpp:{qname}"),
                kind="class",
                name=name,
                qualified_name=qname,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="cpp",
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
            _handle_base_classes(ts_node, n, file_path, nodes, edges, source)
            # Walk class body with this class as context
            body = ts_node.child_by_field_name("body")
            if body:
                for child in body.named_children:
                    _walk(child, n, file_path, nodes, edges, source, class_context=n)
            return

    elif ts_node.type == "struct_specifier":
        name_node = ts_node.child_by_field_name("name")
        if name_node:
            name = node_text(name_node, source)
            n = Node(
                id=stable_id(f"type:cpp:{name}"),
                kind="type",
                name=name,
                qualified_name=name,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="cpp",
                metadata={"struct": True},
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
            return

    elif ts_node.type == "function_definition":
        name = _function_name(ts_node, source)
        if name:
            qname = f"{class_context.qualified_name}::{name}" if class_context else name
            kind = "method" if class_context else "function"
            n = Node(
                id=stable_id(f"function:cpp:{qname}"),
                kind=kind,
                name=name,
                qualified_name=qname,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="cpp",
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
            current = n

    elif ts_node.type == "field_declaration":
        # Method declaration (pure virtual or declared-not-defined) vs plain data member
        fn_decl = _find_function_declarator(ts_node)
        if fn_decl and class_context:
            name = _declarator_name(fn_decl, source)
            if name:
                qname = f"{class_context.qualified_name}::{name}"
                n = Node(
                    id=stable_id(f"function:cpp:{qname}"),
                    kind="method",
                    name=name,
                    qualified_name=qname,
                    file_path=file_path,
                    line_start=ts_node.start_point[0] + 1,
                    line_end=ts_node.end_point[0] + 1,
                    language="cpp",
                    metadata={"declaration_only": True},
                )
                nodes.append(n)
                edges.append(contains_edge(parent, n, file_path, ts_node))
        return  # don't recurse into field declarations

    elif ts_node.type == "template_declaration":
        # Walk into the template body, keeping the same context
        for child in ts_node.named_children:
            _walk(child, current, file_path, nodes, edges, source, class_context)
        return

    elif ts_node.type == "preproc_include":
        _handle_include(ts_node, current, file_path, nodes, edges, source)
        return

    elif ts_node.type == "call_expression":
        _handle_call(ts_node, current, file_path, edges, source)

    for child in ts_node.named_children:
        _walk(child, current, file_path, nodes, edges, source, class_context)


def _find_function_declarator(ts_node: TSNode) -> TSNode | None:
    """Return the function_declarator child of a field_declaration, if any."""
    for child in ts_node.named_children:
        if child.type == "function_declarator":
            return child
        if child.type == "pointer_declarator":
            inner = _find_function_declarator(child)
            if inner:
                return inner
    return None


def _handle_base_classes(
    class_node: TSNode, child: Node, file_path: str,
    nodes: list[Node], edges: list[Edge], source: bytes,
) -> None:
    """Extract inheritance edges from base_class_clause."""
    base_clause = None
    for c in class_node.named_children:
        if c.type == "base_class_clause":
            base_clause = c
            break
    if base_clause is None:
        return
    for base in base_clause.named_children:
        if base.type in ("type_identifier", "qualified_identifier", "identifier"):
            parent_name = node_text(base, source)
            parent_id = stable_id(f"class:cpp:{parent_name}")
            edges.append(inherits_edge(child, parent_id, file_path, base_clause))
