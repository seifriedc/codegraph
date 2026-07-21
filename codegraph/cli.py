from __future__ import annotations
from pathlib import Path
from typing import Optional
import json

import typer

app = typer.Typer(help="codegraph — source code knowledge graph tool", no_args_is_help=True)
query_app = typer.Typer(help="Query the knowledge graph", no_args_is_help=True)
graph_app = typer.Typer(help="Mutate the knowledge graph", no_args_is_help=True)
ast_app = typer.Typer(help="Query and inspect ASTs directly", no_args_is_help=True)
app.add_typer(query_app, name="query")
app.add_typer(graph_app, name="graph")
app.add_typer(ast_app, name="ast")

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


@query_app.command("demographics")
def query_demographics(
    db: Path = _DB_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Report codebase composition: node/edge/LOC breakdown by language and kind."""
    from codegraph.query import Graph

    g = Graph(db)
    report = g.demographics()

    if json_output:
        typer.echo(json.dumps(report, indent=2, default=str))
        return

    typer.echo(f"Codebase demographics — {db}")
    typer.echo("=" * 40)
    typer.echo(f"Files: {report['total_files']}   Nodes: {report['total_nodes']}   Edges: {report['total_edges']}")
    typer.echo(f"Lines: {report['total_lines']}   SLOC: {report['total_sloc']}")

    typer.echo("\nBy language:")
    for language, entry in sorted(report["by_language"].items(), key=lambda kv: (kv[0] is None, kv[0])):
        label = language or "(unknown)"
        typer.echo(f"  {label:<10} {entry['files']:>5} files   {entry['lines']:>7} lines   {entry['sloc']:>7} sloc")

    typer.echo("\nNodes by kind:")
    for kind, count in report["nodes_by_kind"].items():
        typer.echo(f"  {kind:<12} {count}")

    typer.echo("\nEdges by kind:")
    for kind, count in report["edges_by_kind"].items():
        typer.echo(f"  {kind:<12} {count}")


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


_LANG_OPTION = typer.Option(None, "--language", "-l", help="Restrict to language: ada, c, cpp")
_PATH_ARG_OPT = typer.Argument(None, help="Source directory to search (default: use --db)")


@ast_app.command("dump")
def ast_dump(
    file: Path = typer.Argument(..., help="Source file to dump"),
    named_only: bool = typer.Option(False, "--named-only", help="Show only named nodes"),
) -> None:
    """Dump the raw AST of a source file to stdout."""
    from codegraph.ast_query import dump_ast

    try:
        typer.echo(dump_ast(file, named_only=named_only))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)


@ast_app.command("query")
def ast_query_cmd(
    pattern: str = typer.Argument(..., help="S-expression pattern with at least one @capture"),
    path: Optional[Path] = _PATH_ARG_OPT,
    db: Path = _DB_OPTION,
    language: Optional[str] = _LANG_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Warn when pattern is skipped for a language"),
) -> None:
    """Run a tree-sitter S-expression pattern across source files."""
    from codegraph.ast_query import query_files, resolve_files, format_match, _match_to_dict

    files = resolve_files(path, db if db.exists() else None)
    if not files:
        typer.echo("No source files found.", err=True)
        raise typer.Exit(1)

    try:
        matches = list(query_files(pattern, files, language=language, verbose=verbose))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps([_match_to_dict(m) for m in matches], indent=2, default=str))
    else:
        for m in matches:
            typer.echo(format_match(m))
        count = len(matches)
        typer.echo(f"({count} match{'es' if count != 1 else ''})", err=True)


@ast_app.command("shell")
def ast_shell_cmd(
    path: Optional[Path] = _PATH_ARG_OPT,
    db: Path = _DB_OPTION,
    language: Optional[str] = _LANG_OPTION,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Interactive REPL for querying ASTs with S-expression patterns."""
    from codegraph.ast_query import resolve_files, run_repl

    files = resolve_files(path, db if db.exists() else None)
    if not files:
        typer.echo("No source files found.", err=True)
        raise typer.Exit(1)

    run_repl(files, language=language, verbose=verbose)
