from __future__ import annotations
import concurrent.futures
import re
from pathlib import Path
from typing import Any

import duckdb

from codegraph.db import connect

# Comment syntax per language, used for the SLOC heuristic in Graph.demographics().
# Approximate: doesn't special-case comment markers inside string literals.
_LINE_COMMENT = {"ada": "--", "c": "//", "cpp": "//"}
_BLOCK_COMMENT_RE = {
    lang: re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    for lang, (start, end) in {"c": ("/*", "*/"), "cpp": ("/*", "*/")}.items()
}


def _count_loc_sloc(file_path: str | None, language: str | None) -> tuple[int, int] | None:
    """Return (total lines, source lines of code) for a file, or None if unreadable."""
    if not file_path:
        return None
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    total = len(text.splitlines())

    block_re = _BLOCK_COMMENT_RE.get(language)
    stripped = block_re.sub("", text) if block_re else text
    line_comment = _LINE_COMMENT.get(language)

    sloc = 0
    for line in stripped.splitlines():
        code = line.strip()
        if line_comment:
            code = code.split(line_comment, 1)[0].strip()
        if code:
            sloc += 1
    return total, sloc


class Graph:
    """Read-only query interface over an indexed codegraph database."""

    def __init__(self, db_path: str | Path, read_only: bool = False):
        self.conn = connect(db_path, read_only=read_only)

    def cursor(self) -> "Graph":
        """A Graph on a new cursor of this connection, for use in one thread/request."""
        g = Graph.__new__(Graph)
        g.conn = self.conn.cursor()
        return g

    # ── Low-level helpers ─────────────────────────────────────────────────────

    def _fetchall(self, sql: str, params: list[Any] | None = None) -> list[dict]:
        result = self.conn.execute(sql, params or [])
        cols = [d[0] for d in result.description]
        return [dict(zip(cols, row)) for row in result.fetchall()]

    # ── Node queries ──────────────────────────────────────────────────────────

    def nodes(self, **filters: Any) -> list[dict]:
        """Return nodes matching all provided field=value filters."""
        where_parts, params = [], []
        for key, val in filters.items():
            where_parts.append(f"{key} = ?")
            params.append(val)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        return self._fetchall(f"SELECT * FROM nodes {where}", params)

    def resolve_node(self, identifier: str) -> dict | None:
        """Return a node by ID or qualified name, trying ID first."""
        return self.node_by_id(identifier) or self.node_by_qualified_name(identifier)

    def node_by_id(self, node_id: str) -> dict | None:
        rows = self._fetchall("SELECT * FROM nodes WHERE id = ?", [node_id])
        return rows[0] if rows else None

    def node_by_qualified_name(self, qualified_name: str) -> dict | None:
        rows = self._fetchall(
            "SELECT * FROM nodes WHERE qualified_name = ?", [qualified_name]
        )
        return rows[0] if rows else None

    def node_by_name(self, name: str) -> list[dict]:
        return self._fetchall(
            "SELECT * FROM nodes WHERE qualified_name = ? OR name = ?", [name, name]
        )

    # ── Edge queries ──────────────────────────────────────────────────────────

    def edges_from(self, node_id: str, kinds: list[str] | None = None) -> list[dict]:
        if kinds:
            ph = ", ".join("?" * len(kinds))
            return self._fetchall(
                f"SELECT * FROM edges WHERE source_id = ? AND kind IN ({ph})",
                [node_id, *kinds],
            )
        return self._fetchall("SELECT * FROM edges WHERE source_id = ?", [node_id])

    def edges_to(self, node_id: str, kinds: list[str] | None = None) -> list[dict]:
        if kinds:
            ph = ", ".join("?" * len(kinds))
            return self._fetchall(
                f"SELECT * FROM edges WHERE target_id = ? AND kind IN ({ph})",
                [node_id, *kinds],
            )
        return self._fetchall("SELECT * FROM edges WHERE target_id = ?", [node_id])

    # ── Traversal ─────────────────────────────────────────────────────────────

    def traverse(
        self,
        node_id: str,
        edge_kinds: list[str] | None = None,
        direction: str = "out",
        max_depth: int = 1,
    ) -> list[dict]:
        """BFS via DuckDB recursive CTE. direction='out' follows source→target; 'in' reverses."""
        join_col, reach_col = ("source_id", "target_id") if direction == "out" else ("target_id", "source_id")

        kind_filter, kind_params = "", []
        if edge_kinds:
            ph = ", ".join("?" * len(edge_kinds))
            kind_filter = f"AND e.kind IN ({ph})"
            kind_params = list(edge_kinds)

        sql = f"""
            WITH RECURSIVE reach(node_id, depth) AS (
                SELECT ?, 0
                UNION
                SELECT e.{reach_col}, r.depth + 1
                FROM reach r
                JOIN edges e ON e.{join_col} = r.node_id
                WHERE r.depth < ? {kind_filter}
            )
            SELECT DISTINCT n.*
            FROM reach r
            JOIN nodes n ON n.id = r.node_id
            WHERE r.node_id != ?
            ORDER BY n.kind, n.qualified_name
        """
        return self._fetchall(sql, [node_id, max_depth, *kind_params, node_id])

    def transitive(
        self, node_id: str, edge_kind: str, direction: str = "out"
    ) -> list[dict]:
        """Full transitive closure along a single edge kind."""
        return self.traverse(node_id, edge_kinds=[edge_kind], direction=direction, max_depth=999)

    # ── High-level queries ────────────────────────────────────────────────────

    def declaration_hierarchy(self, node_id: str) -> list[dict]:
        """Return all nodes structurally contained within the given node."""
        return self.traverse(
            node_id, edge_kinds=["contains", "defines"], direction="out", max_depth=999
        )

    def nodes_used_by(self, node_id: str) -> list[dict]:
        """All nodes directly referenced/called/imported by the given node."""
        return self.traverse(
            node_id, edge_kinds=["calls", "references", "imports"], direction="out", max_depth=1
        )

    def type_hierarchy(self, node_id: str) -> dict[str, list[dict]]:
        """Return ancestors (parent types) and descendants (child types) of a type."""
        return {
            "ancestors": self.transitive(node_id, "inherits", direction="out"),
            "descendants": self.transitive(node_id, "inherits", direction="in"),
        }

    def demographics(self) -> dict:
        """Summary of the indexed codebase: node/edge/LOC counts broken down by language and kind."""
        nodes_by_language = {
            row["language"]: row["count"]
            for row in self._fetchall(
                "SELECT language, COUNT(*) AS count FROM nodes GROUP BY language ORDER BY language"
            )
        }
        nodes_by_kind = {
            row["kind"]: row["count"]
            for row in self._fetchall(
                "SELECT kind, COUNT(*) AS count FROM nodes GROUP BY kind ORDER BY kind"
            )
        }
        edges_by_kind = {
            row["kind"]: row["count"]
            for row in self._fetchall(
                "SELECT kind, COUNT(*) AS count FROM edges GROUP BY kind ORDER BY kind"
            )
        }

        by_language: dict[str, dict] = {}

        def lang_entry(language: str) -> dict:
            return by_language.setdefault(
                language, {"nodes_by_kind": {}, "files": 0, "lines": 0, "sloc": 0}
            )

        for row in self._fetchall(
            "SELECT language, kind, COUNT(*) AS count FROM nodes GROUP BY language, kind ORDER BY language, kind"
        ):
            lang_entry(row["language"])["nodes_by_kind"][row["kind"]] = row["count"]

        file_rows = self._fetchall("SELECT language, file_path FROM nodes WHERE kind = 'file'")
        with concurrent.futures.ThreadPoolExecutor() as pool:
            counts = pool.map(lambda r: _count_loc_sloc(r["file_path"], r["language"]), file_rows)

        for row, count in zip(file_rows, counts):
            entry = lang_entry(row["language"])
            entry["files"] += 1
            if count is not None:
                lines, sloc = count
                entry["lines"] += lines
                entry["sloc"] += sloc

        return {
            "total_nodes": sum(nodes_by_language.values()),
            "total_edges": sum(edges_by_kind.values()),
            "total_files": sum(entry["files"] for entry in by_language.values()),
            "total_lines": sum(entry["lines"] for entry in by_language.values()),
            "total_sloc": sum(entry["sloc"] for entry in by_language.values()),
            "nodes_by_language": nodes_by_language,
            "nodes_by_kind": nodes_by_kind,
            "edges_by_kind": edges_by_kind,
            "by_language": by_language,
        }

    def callers(self, node_id: str) -> list[dict]:
        """All nodes that directly call the given node."""
        edges = self.edges_to(node_id, kinds=["calls"])
        if not edges:
            return []
        ids = list({e["source_id"] for e in edges})
        ph = ", ".join("?" * len(ids))
        return self._fetchall(f"SELECT * FROM nodes WHERE id IN ({ph})", ids)

    def ast(self, file_path: str) -> dict:
        """Return raw AST for a file (requires Rust extension; not yet implemented)."""
        raise NotImplementedError(
            "ast() requires the Rust extension (codegraph_core). "
            "Run `maturin develop` to build it."
        )

    def close(self) -> None:
        self.conn.close()
