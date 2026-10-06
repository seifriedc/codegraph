from __future__ import annotations
from pathlib import Path

from tree_sitter import Language, Parser, Node as TSNode
import tree_sitter_ada

from codegraph.models import Node, Edge, stable_id
from codegraph.parsers.base import (
    make_file_node,
    node_text,
    contains_edge,
    imports_edge,
    calls_edge,
    inherits_edge,
    references_edge,
    external_node,
)

_LANGUAGE = Language(tree_sitter_ada.language())
_PARSER = Parser(_LANGUAGE)

# Containers we recurse through without creating a node
_TRANSPARENT = {
    "compilation",
    "compilation_unit",
    "non_empty_declarative_part",
    "declarative_part",
    "handled_sequence_of_statements",
    "sequence_of_statements",
    "record_definition",
    "record_extension_part",
    "component_list",
}


def parse(path: Path) -> tuple[list[Node], list[Edge]]:
    source = path.read_bytes()
    tree = _PARSER.parse(source)
    fp = str(path)

    nodes: list[Node] = []
    edges: list[Edge] = []

    file_node = make_file_node(path, "ada")
    nodes.append(file_node)

    _walk(tree.root_node, file_node, fp, nodes, edges, source, parent_qname=None)
    return nodes, edges


def _selected_name(ts_node: TSNode, source: bytes) -> str:
    """Recursively build dotted name from selected_component or identifier."""
    if ts_node.type == "identifier":
        return node_text(ts_node, source)
    if ts_node.type == "selected_component" and len(ts_node.named_children) >= 2:
        left = _selected_name(ts_node.named_children[0], source)
        right = _selected_name(ts_node.named_children[1], source)
        return f"{left}.{right}"
    return node_text(ts_node, source)


def _first_name(ts_node: TSNode, source: bytes) -> tuple[str, bool] | tuple[None, bool]:
    """Return (dotted_name, is_already_qualified) for the first identifier or selected_component child.

    is_already_qualified is True when the name is a selected_component (e.g. 'Outer.Inner'),
    meaning it should not be prefixed with parent_qname.
    """
    for child in ts_node.named_children:
        if child.type == "identifier":
            return node_text(child, source), False
        if child.type == "selected_component":
            return _selected_name(child, source), True
    return None, False


def _subprogram_spec(ts_node: TSNode) -> TSNode | None:
    """Return the function_specification or procedure_specification child."""
    for child in ts_node.named_children:
        if child.type in ("function_specification", "procedure_specification"):
            return child
    return None


def _resolve_type_name(raw: str, current_qname: str | None) -> str:
    if "." not in raw and current_qname:
        dot = current_qname.rfind(".")
        return f"{current_qname[:dot]}.{raw}" if dot != -1 else raw
    return raw


def _emit_type_ref(
    name_node: TSNode,
    current: Node,
    current_qname: str | None,
    file_path: str,
    nodes: list[Node],
    edges: list[Edge],
    source: bytes,
) -> None:
    raw = _selected_name(name_node, source)
    type_name = _resolve_type_name(raw, current_qname)
    type_id = stable_id(f"type:ada:{type_name}")
    nodes.append(external_node(type_name, "ada", "type"))
    edges.append(references_edge(current.id, type_id, file_path, name_node))


def _walk(
    ts_node: TSNode,
    parent: Node,
    file_path: str,
    nodes: list[Node],
    edges: list[Edge],
    source: bytes,
    parent_qname: str | None,
) -> None:
    if ts_node.type in _TRANSPARENT:
        for child in ts_node.named_children:
            _walk(child, parent, file_path, nodes, edges, source, parent_qname)
        return

    current = parent
    current_qname = parent_qname

    if ts_node.type in ("package_declaration", "package_body"):
        full_name, is_qualified = _first_name(ts_node, source)
        if full_name:
            # Dotted names (child units) are already fully qualified; a simple name
            # nested inside another package inherits the enclosing package's scope.
            qname = full_name if is_qualified or not parent_qname else f"{parent_qname}.{full_name}"
            name = qname.split(".")[-1]
            n = Node(
                id=stable_id(f"package:ada:{qname}"),
                kind="package",
                name=name,
                qualified_name=qname,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="ada",
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
            # Package nesting: parent package contains child package (ADR 0001).
            # Physical nesting already has the parent package as `parent`; child
            # units (Geometry.Utils) are parented by the name prefix.
            if "." in qname and parent.kind != "package":
                parent_pkg_name = qname.rsplit(".", 1)[0]
                parent_pkg = external_node(parent_pkg_name, "ada", "package")
                nodes.append(parent_pkg)
                edges.append(contains_edge(parent_pkg, n, file_path, ts_node))
            current = n
            current_qname = qname

    elif ts_node.type in ("subprogram_declaration", "subprogram_body"):
        spec = _subprogram_spec(ts_node)
        if spec:
            raw_name, is_qualified = _first_name(spec, source)
            if raw_name:
                # Already-qualified names (e.g. library-unit body "function Pkg.Foo")
                # must not be prefixed again; simple names inherit parent scope.
                qname = (
                    raw_name
                    if is_qualified
                    else (f"{parent_qname}.{raw_name}" if parent_qname else raw_name)
                )
                name = raw_name.split(".")[-1]
                kind = "function"  # covers both Ada functions and procedures
                n = Node(
                    id=stable_id(f"function:ada:{qname}"),
                    kind=kind,
                    name=name,
                    qualified_name=qname,
                    file_path=file_path,
                    line_start=ts_node.start_point[0] + 1,
                    line_end=ts_node.end_point[0] + 1,
                    language="ada",
                    metadata={"subkind": spec.type.split("_")[0]},  # "function" or "procedure"
                )
                nodes.append(n)
                edges.append(contains_edge(parent, n, file_path, ts_node))
                current = n
                current_qname = qname

    elif ts_node.type == "full_type_declaration":
        name, _ = _first_name(ts_node, source)
        if name:
            qname = f"{parent_qname}.{name}" if parent_qname else name
            n = Node(
                id=stable_id(f"type:ada:{qname}"),
                kind="type",
                name=name,
                qualified_name=qname,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="ada",
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
            # Check for derived type (inherits edge)
            for child in ts_node.named_children:
                if child.type == "derived_type_definition":
                    parent_name, _ = _first_name(child, source)
                    if parent_name:
                        parent_id = stable_id(f"type:ada:{parent_name}")
                        edges.append(inherits_edge(n, parent_id, file_path, child))
            current = n
            current_qname = qname

    elif ts_node.type == "with_clause":
        for child in ts_node.named_children:
            if child.type in ("identifier", "selected_component"):
                pkg_name = _selected_name(child, source)
                ext = external_node(pkg_name, "ada", "package")
                nodes.append(ext)
                edges.append(imports_edge(parent, ext, file_path, ts_node))
        return  # no further descent

    elif ts_node.type in ("procedure_call_statement", "function_call"):
        # Skip Ada attribute calls (e.g. Positive'Max) — they have a tick child
        is_attribute_call = any(c.type == "tick" for c in ts_node.named_children)
        if not is_attribute_call:
            name_child = ts_node.named_children[0] if ts_node.named_children else None
            if name_child:
                raw_name = _selected_name(name_child, source)
                # Resolve unqualified names against the enclosing package scope
                if "." not in raw_name and current_qname:
                    dot = current_qname.rfind(".")
                    callee_name = f"{current_qname[:dot]}.{raw_name}" if dot != -1 else raw_name
                else:
                    callee_name = raw_name
                callee_id = stable_id(f"function:ada:{callee_name}")
                # Placeholder node so the callee is queryable even if not indexed
                nodes.append(external_node(callee_name, "ada", "function"))
                edges.append(calls_edge(current, callee_id, file_path, ts_node))
        # Fall through to recurse into arguments — catches nested function calls

    elif ts_node.type == "component_declaration":
        # Collect all names before component_definition (e.g. "X, Y : Float" has two)
        field_names = []
        for child in ts_node.named_children:
            if child.type == "component_definition":
                break
            if child.type == "identifier":
                field_names.append(node_text(child, source))
        if field_names and parent_qname:
            for field_name in field_names:
                qname = f"{parent_qname}.{field_name}"
                n = Node(
                    id=stable_id(f"field:ada:{qname}"),
                    kind="field",
                    name=field_name,
                    qualified_name=qname,
                    file_path=file_path,
                    line_start=ts_node.start_point[0] + 1,
                    line_end=ts_node.end_point[0] + 1,
                    language="ada",
                )
                nodes.append(n)
                edges.append(contains_edge(parent, n, file_path, ts_node))
        # Fall through so component_definition child is visited for the type reference

    elif ts_node.type == "component_definition":
        # First identifier/selected_component is the field's type
        name_child = next(
            (c for c in ts_node.named_children if c.type in ("identifier", "selected_component")),
            None,
        )
        if name_child:
            _emit_type_ref(name_child, current, current_qname, file_path, nodes, edges, source)
        return

    elif ts_node.type == "parameter_specification":
        # Last identifier/selected_component is the type; preceding ones are param names
        name_child = None
        for c in ts_node.named_children:
            if c.type in ("identifier", "selected_component"):
                name_child = c
        if name_child:
            _emit_type_ref(name_child, current, current_qname, file_path, nodes, edges, source)
        return

    elif ts_node.type == "result_profile":
        # Single child is the return type
        name_child = next(
            (c for c in ts_node.named_children if c.type in ("identifier", "selected_component")),
            None,
        )
        if name_child:
            _emit_type_ref(name_child, current, current_qname, file_path, nodes, edges, source)
        return

    elif ts_node.type == "generic_instantiation":
        raw_name, is_qualified = _first_name(ts_node, source)
        if raw_name:
            name = raw_name.split(".")[-1]
            qname = (
                raw_name
                if is_qualified
                else (f"{parent_qname}.{raw_name}" if parent_qname else raw_name)
            )
            n = Node(
                id=stable_id(f"package:ada:{qname}"),
                kind="package",
                name=name,
                qualified_name=qname,
                file_path=file_path,
                line_start=ts_node.start_point[0] + 1,
                line_end=ts_node.end_point[0] + 1,
                language="ada",
            )
            nodes.append(n)
            edges.append(contains_edge(parent, n, file_path, ts_node))
            # The generic being instantiated is the second selected_component/identifier
            for i, child in enumerate(ts_node.named_children):
                if i > 0 and child.type in ("identifier", "selected_component"):
                    generic_id = stable_id(f"package:ada:{_selected_name(child, source)}")
                    edges.append(
                        Edge(
                            kind="instantiates",
                            source_id=n.id,
                            target_id=generic_id,
                            file_path=file_path,
                            line=ts_node.start_point[0] + 1,
                            col=ts_node.start_point[1],
                        )
                    )
                    break

    for child in ts_node.named_children:
        _walk(child, current, file_path, nodes, edges, source, current_qname)
