from __future__ import annotations
from pathlib import Path
from typing import Optional
import json

import typer

app = typer.Typer(help="codegraph — source code knowledge graph tool", no_args_is_help=True)
query_app = typer.Typer(help="Query the knowledge graph", no_args_is_help=True)
graph_app = typer.Typer(help="Mutate the knowledge graph", no_args_is_help=True)
app.add_typer(query_app, name="query")
app.add_typer(graph_app, name="graph")

_DB_OPTION = typer.Option(Path(".codegraph.db"), "--db", help="Path to .duckdb file")


def _resolve_or_exit(g, identifier: str):
    """Resolve a node ID or qualified name, exiting with an error if not found."""
    from codegraph.query import Graph
    node = g.resolve_node(identifier)
    if node is None:
        typer.echo(f"Error: node not found: {identifier!r}", err=True)
        raise typer.Exit(1)
    return node


@app.command()
def index(
    path: Path = typer.Argument(default=Path("."), help="Directory to index (default: current directory)"),
    db: Path = _DB_OPTION,
) -> None:
    """Walk a source tree and build the knowledge graph."""
    from codegraph.indexer import Indexer

    indexer = Indexer(db)
    count = indexer.index(path)
    indexer.close()
    typer.echo(f"Indexed {count} file(s) → {db}")


@query_app.command("node")
def query_node(
    node: str = typer.Argument(..., help="Node ID or qualified name"),
    db: Path = _DB_OPTION,
) -> None:
    """Look up a single node by ID or qualified name."""
    from codegraph.query import Graph

    g = Graph(db)
    result = _resolve_or_exit(g, node)
    typer.echo(json.dumps(result, indent=2, default=str))


@query_app.command("nodes")
def query_nodes(
    db: Path = _DB_OPTION,
    kind: Optional[str] = typer.Option(None),
    language: Optional[str] = typer.Option(None),
    name: Optional[str] = typer.Option(None),
) -> None:
    """List nodes, optionally filtered by kind/language/name."""
    from codegraph.query import Graph

    g = Graph(db)
    filters = {k: v for k, v in [("kind", kind), ("language", language), ("name", name)] if v}
    rows = g.nodes(**filters)
    typer.echo(json.dumps(rows, indent=2, default=str))


@query_app.command("traverse")
def query_traverse(
    node: str = typer.Argument(..., help="Node ID or qualified name"),
    db: Path = _DB_OPTION,
    edge_kinds: Optional[str] = typer.Option(None, "--edge-kinds", help="Comma-separated"),
    direction: str = typer.Option("out", "--direction"),
    depth: int = typer.Option(1, "--depth"),
) -> None:
    """BFS traversal from a node."""
    from codegraph.query import Graph

    g = Graph(db)
    node_id = _resolve_or_exit(g, node)["id"]
    kinds = edge_kinds.split(",") if edge_kinds else None
    rows = g.traverse(node_id, edge_kinds=kinds, direction=direction, max_depth=depth)
    typer.echo(json.dumps(rows, indent=2, default=str))


@query_app.command("hierarchy")
def query_hierarchy(
    node: str = typer.Argument(..., help="Node ID or qualified name"),
    db: Path = _DB_OPTION,
) -> None:
    """Declaration hierarchy for a package or class."""
    from codegraph.query import Graph

    g = Graph(db)
    node_id = _resolve_or_exit(g, node)["id"]
    rows = g.declaration_hierarchy(node_id)
    typer.echo(json.dumps(rows, indent=2, default=str))


@query_app.command("uses")
def query_uses(
    node: str = typer.Argument(..., help="Node ID or qualified name"),
    db: Path = _DB_OPTION,
) -> None:
    """All nodes directly used (called/referenced/imported) by a node."""
    from codegraph.query import Graph

    g = Graph(db)
    node_id = _resolve_or_exit(g, node)["id"]
    rows = g.nodes_used_by(node_id)
    typer.echo(json.dumps(rows, indent=2, default=str))


@query_app.command("type-hierarchy")
def query_type_hierarchy(
    node: str = typer.Argument(..., help="Node ID or qualified name"),
    db: Path = _DB_OPTION,
) -> None:
    """Ancestors and descendants of a type."""
    from codegraph.query import Graph

    g = Graph(db)
    node_id = _resolve_or_exit(g, node)["id"]
    result = g.type_hierarchy(node_id)
    typer.echo(json.dumps(result, indent=2, default=str))


@query_app.command("callers")
def query_callers(
    node: str = typer.Argument(..., help="Node ID or qualified name"),
    db: Path = _DB_OPTION,
) -> None:
    """All nodes that call the given node."""
    from codegraph.query import Graph

    g = Graph(db)
    node_id = _resolve_or_exit(g, node)["id"]
    rows = g.callers(node_id)
    typer.echo(json.dumps(rows, indent=2, default=str))


@graph_app.command("add-node")
def graph_add_node(
    db: Path = _DB_OPTION,
    kind: str = typer.Option(...),
    name: str = typer.Option(...),
    language: str = typer.Option(...),
    qualified_name: Optional[str] = typer.Option(None),
    file_path: Optional[str] = typer.Option(None),
) -> None:
    """Add a node to the graph."""
    from codegraph.indexer import Indexer

    idx = Indexer(db)
    nid = idx.add_node(kind=kind, name=name, language=language,
                       qualified_name=qualified_name, file_path=file_path)
    idx.close()
    typer.echo(nid)


@graph_app.command("add-edge")
def graph_add_edge(
    db: Path = _DB_OPTION,
    kind: str = typer.Option(...),
    source: str = typer.Option(..., help="Source node ID or qualified name"),
    target: str = typer.Option(..., help="Target node ID or qualified name"),
    file_path: Optional[str] = typer.Option(None),
    line: Optional[int] = typer.Option(None),
    col: Optional[int] = typer.Option(None),
) -> None:
    """Add an edge to the graph."""
    from codegraph.indexer import Indexer
    from codegraph.query import Graph

    g = Graph(db)
    source_id = _resolve_or_exit(g, source)["id"]
    target_id = _resolve_or_exit(g, target)["id"]
    idx = Indexer(db)
    eid = idx.add_edge(kind=kind, source_id=source_id, target_id=target_id,
                       file_path=file_path, line=line, col=col)
    idx.close()
    typer.echo(eid)
