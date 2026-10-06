from __future__ import annotations
from pathlib import Path

import duckdb

from codegraph.db import connect, insert_nodes, insert_edges
from codegraph.models import Node, Edge, stable_id, random_id
from codegraph.parsers import detect_language


class Indexer:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = connect(self.db_path)

    def index(self, root: Path, *, skip_hidden: bool = True) -> int:
        """Walk root, parse supported files, persist nodes and edges. Returns file count."""
        count = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if skip_hidden and any(p.startswith(".") for p in path.relative_to(root).parts):
                continue
            language = detect_language(path)
            if language is None:
                continue
            nodes, edges = self._parse_file(path, language)
            insert_nodes(self.conn, nodes)
            insert_edges(self.conn, edges)
            count += 1
        return count

    def _parse_file(self, path: Path, language: str) -> tuple[list[Node], list[Edge]]:
        from codegraph.parsers import ada_parser, c_parser, cpp_parser

        dispatch = {
            "ada": ada_parser.parse,
            "c": c_parser.parse,
            "cpp": cpp_parser.parse,
        }
        parser_fn = dispatch.get(language)
        if parser_fn is None:
            from codegraph.parsers.base import make_file_node
            return [make_file_node(path, language)], []
        return parser_fn(path)

    # ── Mutation API ──────────────────────────────────────────────────────────

    def add_node(
        self,
        kind: str,
        name: str,
        language: str,
        qualified_name: str | None = None,
        file_path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        metadata: dict | None = None,
    ) -> str:
        n = Node(
            id=stable_id(f"{kind}:{language}:{qualified_name}") if qualified_name else random_id(),
            kind=kind,
            name=name,
            language=language,
            qualified_name=qualified_name,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            metadata=metadata or {},
        )
        insert_nodes(self.conn, [n])
        return n.id

    def add_edge(
        self,
        kind: str,
        source_id: str,
        target_id: str,
        file_path: str | None = None,
        line: int | None = None,
        col: int | None = None,
    ) -> str:
        e = Edge(kind=kind, source_id=source_id, target_id=target_id,
                 file_path=file_path, line=line, col=col)
        insert_edges(self.conn, [e])
        return e.id

    def update_node_metadata(self, node_id: str, metadata: dict) -> None:
        import json
        self.conn.execute(
            "UPDATE nodes SET metadata = ? WHERE id = ?",
            (json.dumps(metadata), node_id),
        )

    def close(self) -> None:
        self.conn.close()
