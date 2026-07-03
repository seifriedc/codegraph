from __future__ import annotations
import json
from pathlib import Path
from typing import Any

import duckdb

from codegraph.db import connect
from codegraph.codegraph_core import traverse as _rust_traverse


class Graph:
    """Read-only query interface over an indexed codegraph database."""

    def __init__(self, db_path: str | Path):
        self.conn = connect(db_path)

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
        """BFS traversal via Rust. direction='out' follows source→target; 'in' reverses."""
        if edge_kinds:
            ph = ", ".join("?" * len(edge_kinds))
            edges = self._fetchall(
                f"SELECT source_id, target_id, kind FROM edges WHERE kind IN ({ph})",
                list(edge_kinds),
            )
        else:
            edges = self._fetchall("SELECT source_id, target_id, kind FROM edges")

        reachable_ids: list[str] = json.loads(
            _rust_traverse(node_id, json.dumps(edges), edge_kinds or [], direction, max_depth)
        )
        if not reachable_ids:
            return []

        ph = ", ".join("?" * len(reachable_ids))
        return self._fetchall(
            f"SELECT * FROM nodes WHERE id IN ({ph}) ORDER BY kind, qualified_name",
            reachable_ids,
        )

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
