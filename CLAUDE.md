# CLAUDE.md

A polyglot source code knowledge graph tool: indexes a repository into nodes (files, packages, functions, classes, types) and edges (imports, calls, defines, contains, inherits, instantiates) in an embedded DuckDB database. Use cases: navigation, impact analysis, LLM context assembly, type hierarchy traversal.

## Dev setup and checks

```bash
uv venv --python 3.12 && source .venv/bin/activate && uv pip install ".[dev]"
pre-commit install   # ruff, pytest and node tests run on commit; CI runs the same
```

`codegraph --help` and `codegraph <group> --help` list the CLI (`index`, `query`, `graph`, `ast`, `serve`).

## Layout

- `codegraph/parsers/` — one tree-sitter parser per language, all with the contract `parse(path) -> (nodes, edges)`.
- `codegraph/indexer.py` — `Indexer`: walks files, dispatches to parsers, batch-inserts; also the mutation API (`add_node`, `add_edge`, `update_node_metadata`).
- `codegraph/db.py` — DuckDB connection and schema DDL.
- `codegraph/query.py` — `Graph`: traversal API, including recursive-CTE transitive queries.
- `codegraph/cli.py` — Typer CLI.
- `codegraph/vis/` — the `codegraph serve` FastAPI app and committed static UI (vendored libraries in `static/vendor/`, no node build step).
  - It consumes `Graph` only and contains **no SQL** (ADR 0002). New query primitives go on `Graph`; JSON shaping, limits, relative paths and HTTP stay in `vis`.
  - Read-only and stateless: `Graph(db, read_only=True)`, one cursor per request, view state in the URL hash.
- Vocabulary: `GLOSSARY.md`. Decisions: `docs/adr/`.

## Node and edge IDs

IDs are deterministic `uuid5` hashes, so re-indexing yields the same IDs. They are name-based and exclude `file_path`, so cross-file `inherits`/`calls` edges resolve without a resolution pass.

- Ada: `stable_id(f"{kind}:ada:{qualified_name}")`, e.g. `Geometry.Distance`
- C: `stable_id(f"{kind}:c:{name}")`
- C++: `stable_id(f"{kind}:cpp:{qualified_name}")`, e.g. `Circle::area`
- Files: `stable_id(f"file:{absolute_path}")`
- External/unresolved references (e.g. `with Ada.Text_IO`): `stable_id(f"{kind}:{language}:{name}")`
- Edges: derived from kind, endpoints, file path, line, col. `Indexer.add_edge` uses a random ID.

Known limitation: same-named entities (C `static` functions in different files, Ada overloads) collapse into one node (issue #14).

Package nodes and their nesting `contains` edges are materialized at index time; Aggregate edges between Groups are derived at query time, never stored (ADR 0001).

## Testing

Integration tests first; see `docs/testing.md` for the seams, the OpenAPI snapshot workflow and what is not automated.

## Adding a language parser

1. Add `tree-sitter-<lang>` to `pyproject.toml`.
2. Add its extensions to `EXTENSION_TO_LANGUAGE` in `codegraph/parsers/__init__.py`.
3. Create `codegraph/parsers/<lang>_parser.py` with `parse(path)`.
4. Register it in the `Indexer._parse_file()` dispatch dict.
5. Add fixtures under `tests/fixtures/<lang>/` and integration tests in `tests/test_indexer.py`.

## Agent skills

- Issues: GitHub Issues on `seifriedc/codegraph` via `gh`; see `docs/agents/issue-tracker.md`.
- Triage labels: `docs/agents/triage-labels.md`.
- Domain docs (single context): `docs/agents/domain.md`.
