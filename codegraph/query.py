from __future__ import annotations
import concurrent.futures
import os
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


class _Grouping:
    """What an overview grouping strategy returns.

    groups:    {group id: {id, kind, name, qualified_name, file_path, node_id, parent}};
               `node_id` is the real node a Group is (a file, a package), else None.
    placement: {node id: id of the innermost Group it belongs to}; a Group's own node is
               placed in that Group. Nodes absent from `placement` are not shown.
    sizes:     {group id: nodes placed in the Group or any descendant}.
    """

    def __init__(self, groups: dict[str, dict], placement: dict[str, str]):
        self.groups = groups
        self.placement = placement
        self.sizes = {gid: 0 for gid in groups}
        for gid in placement.values():
            while gid is not None:
                self.sizes[gid] += 1
                gid = groups[gid]["parent"]


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

    # ── Neighborhood ──────────────────────────────────────────────────────────

    def neighborhood(
        self,
        node_id: str,
        direction: str = "both",
        depth: int = 1,
        edge_kinds: list[str] | None = None,
        limit: int | None = None,
    ) -> dict | None:
        """Nodes within `depth` of a Focus node, plus every edge among the included nodes.

        direction: 'out' (source to target), 'in' (reverse) or 'both'. Each returned
        node is a node dict with an added `depth` (0 for the focus). `limit` caps the
        node count: the deepest BFS ring is dropped first (a ring that only partly fits
        keeps its first nodes by qualified name). Returns
        {"nodes", "edges", "truncated", "total"} where total is the untruncated node
        count, or None if the focus node does not exist.
        """
        focus = self.node_by_id(node_id)
        if focus is None:
            return None

        kind_sql, kind_params = "", []
        if edge_kinds:
            kind_sql = f"AND e.kind IN ({', '.join('?' * len(edge_kinds))})"
            kind_params = list(edge_kinds)

        steps = {"out": [("source_id", "target_id")], "in": [("target_id", "source_id")],
                 "both": [("source_id", "target_id"), ("target_id", "source_id")]}[direction]

        depth_of: dict[str, int] = {node_id: 0}
        frontier = [node_id]
        for d in range(1, depth + 1):
            if not frontier:
                break
            found: set[str] = set()
            for src_col, dst_col in steps:
                rows = self.conn.execute(
                    f"SELECT DISTINCT e.{dst_col} FROM edges e "
                    f"WHERE e.{src_col} IN (SELECT unnest(?)) {kind_sql}",
                    [frontier, *kind_params],
                ).fetchall()
                found.update(r[0] for r in rows)
            frontier = sorted(i for i in found if i not in depth_of)
            for i in frontier:
                depth_of[i] = d

        rows = self._fetchall(
            "SELECT * FROM nodes WHERE id IN (SELECT unnest(?))", [list(depth_of)]
        )
        for r in rows:
            r["depth"] = depth_of[r["id"]]
        rows.sort(key=lambda r: (r["depth"], r["qualified_name"] or r["name"], r["id"]))
        total = len(rows)
        truncated = limit is not None and total > limit
        if truncated:
            rows = rows[:limit]

        ids = [r["id"] for r in rows]
        edges = self._fetchall(
            f"SELECT * FROM edges e WHERE e.source_id IN (SELECT unnest(?)) "
            f"AND e.target_id IN (SELECT unnest(?)) {kind_sql} ORDER BY e.id",
            [ids, ids, *kind_params],
        )
        return {"nodes": rows, "edges": edges, "truncated": truncated, "total": total}

    # Tie-break order among equally good matches: types and functions before containers and members.
    SEARCH_KIND_PRIORITY = ("class", "type", "function", "method", "package", "module",
                            "file", "variable", "field")

    def search(
        self,
        query: str,
        kinds: list[str] | None = None,
        languages: list[str] | None = None,
        limit: int = 20,
    ) -> dict:
        """Case-insensitive node search, ranked for type-ahead.

        Matches `name` and `qualified_name` (a file's qualified name is its path, so files
        match by name only); `file_path` is matched too only when the query contains '/'
        or '.'. Ranking: exact > prefix > substring (> path-only) match, then kind
        priority, then degree (edge count, descending). Returns
        {nodes, total, truncated}; each node dict gains `degree` and `file_count`
        (number of files that contain it).
        """
        q = query.strip().lower()
        if not q:
            return {"nodes": [], "total": 0, "truncated": False}
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_any, like_prefix = f"%{esc}%", f"{esc}%"
        by_path = "/" in q or "." in q
        qn = "(CASE WHEN n.kind = 'file' THEN NULL ELSE lower(n.qualified_name) END)"
        nm = "lower(n.name)"
        path = "lower(n.file_path)"
        sub = f"({nm} LIKE ? ESCAPE '\\' OR {qn} LIKE ? ESCAPE '\\')"
        path_sql = f" OR {path} LIKE ? ESCAPE '\\'" if by_path else ""
        where = [f"({sub}{path_sql})"]
        params: list[Any] = [like_any, like_any] + ([like_any] if by_path else [])
        for col, vals in (("n.kind", kinds), ("n.language", languages)):
            if vals:
                where.append(f"{col} IN ({', '.join('?' * len(vals))})")
                params += list(vals)
        where_sql = " AND ".join(where)
        total = self.conn.execute(f"SELECT COUNT(*) FROM nodes n WHERE {where_sql}", params).fetchone()[0]
        kind_rank = "CASE n.kind " + " ".join(
            f"WHEN '{k}' THEN {i}" for i, k in enumerate(self.SEARCH_KIND_PRIORITY)
        ) + f" ELSE {len(self.SEARCH_KIND_PRIORITY)} END"
        tier = (f"CASE WHEN {nm} = ? OR {qn} = ? THEN 0 "
                f"WHEN {nm} LIKE ? ESCAPE '\\' OR {qn} LIKE ? ESCAPE '\\' THEN 1 "
                f"WHEN {sub} THEN 2 ELSE 3 END")
        tier_params = [q, q, like_prefix, like_prefix, like_any, like_any]
        rows = self._fetchall(
            f"SELECT n.*, "
            f"(SELECT COUNT(*) FROM edges e WHERE e.source_id = n.id OR e.target_id = n.id) AS degree, "
            f"(SELECT COUNT(DISTINCT e.source_id) FROM edges e JOIN nodes f ON f.id = e.source_id "
            f" WHERE e.target_id = n.id AND e.kind = 'contains' AND f.kind = 'file') AS file_count, "
            f"{tier} AS tier "
            f"FROM nodes n WHERE {where_sql} "
            f"ORDER BY tier, {kind_rank}, degree DESC, lower(n.qualified_name), n.id LIMIT ?",
            tier_params + params + [limit],
        )
        for r in rows:
            del r["tier"]
        return {"nodes": rows, "total": total, "truncated": total > len(rows)}

    def edges_among(self, node_ids: list[str], edge_kinds: list[str] | None = None) -> list[dict]:
        """Every edge whose source and target are both in `node_ids` (optionally of the given kinds)."""
        kind_sql, kind_params = "", []
        if edge_kinds:
            kind_sql = f"AND e.kind IN ({', '.join('?' * len(edge_kinds))})"
            kind_params = list(edge_kinds)
        return self._fetchall(
            f"SELECT * FROM edges e WHERE e.source_id IN (SELECT unnest(?)) "
            f"AND e.target_id IN (SELECT unnest(?)) {kind_sql} ORDER BY e.id",
            [node_ids, node_ids, *kind_params],
        )

    # Edge kinds that carry impact. All point from dependant to dependency (a calls b, a
    # inherits b), so the Impact set follows them backwards (for inherits: descendants)
    # and Dependencies follow them forwards (for inherits: ancestors).
    REACH_KINDS = ["calls", "references", "instantiates", "inherits"]

    def reach(self, node_id: str, mode: str = "both", depth: int = 2,
              limit: int | None = None) -> dict | None:
        """The Impact set ('impact'), the Dependencies ('dependencies') or their union ('both').

        Same result shape as `neighborhood`, plus `ring_counts` {depth: untruncated node
        count} for depth >= 1. In 'both' mode the two sets are expanded independently
        (callers of callees are not included) and merged, keeping the smaller depth.
        """
        directions = {"impact": ["in"], "dependencies": ["out"], "both": ["in", "out"]}[mode]
        parts = [self.neighborhood(node_id, direction=d, depth=depth,
                                   edge_kinds=self.REACH_KINDS) for d in directions]
        if parts[0] is None:
            return None
        nodes: dict[str, dict] = {}
        for p in parts:
            for n in p["nodes"]:
                if n["id"] not in nodes or n["depth"] < nodes[n["id"]]["depth"]:
                    nodes[n["id"]] = n
        rows = sorted(nodes.values(),
                      key=lambda r: (r["depth"], r["qualified_name"] or r["name"], r["id"]))
        ring_counts: dict[int, int] = {}
        for r in rows:
            if r["depth"] >= 1:
                ring_counts[r["depth"]] = ring_counts.get(r["depth"], 0) + 1
        total = len(rows)
        truncated = limit is not None and total > limit
        if truncated:
            rows = rows[:limit]
        kept = {r["id"] for r in rows}
        return {
            "nodes": rows,
            "edges": self._fetchall(
                "SELECT * FROM edges WHERE source_id IN (SELECT unnest(?)) "
                "AND target_id IN (SELECT unnest(?)) AND kind IN (SELECT unnest(?)) ORDER BY id",
                [list(kept), list(kept), self.REACH_KINDS]),
            "truncated": truncated, "total": total, "ring_counts": ring_counts,
        }

    def neighbour_counts(self, node_id: str) -> dict[str, dict[str, int]]:
        """Distinct neighbour nodes per edge kind, split by direction: {"in": {...}, "out": {...}}."""
        out: dict[str, dict[str, int]] = {"in": {}, "out": {}}
        for direction, col, other in (("out", "source_id", "target_id"), ("in", "target_id", "source_id")):
            for kind, count in self.conn.execute(
                f"SELECT kind, COUNT(DISTINCT {other}) FROM edges WHERE {col} = ? "
                f"GROUP BY kind ORDER BY kind",
                [node_id],
            ).fetchall():
                out[direction][kind] = count
        return out

    def defining_files(self, node_id: str) -> list[str]:
        """Paths of every file node that contains the given node, sorted."""
        rows = self.conn.execute(
            "SELECT DISTINCT f.file_path FROM edges e JOIN nodes f ON f.id = e.source_id "
            "WHERE e.target_id = ? AND e.kind = 'contains' AND f.kind = 'file' "
            "AND f.file_path IS NOT NULL ORDER BY f.file_path",
            [node_id],
        ).fetchall()
        return [r[0] for r in rows]

    # ── Overview ──────────────────────────────────────────────────────────────

    def edge_kinds(self) -> list[str]:
        """Distinct edge kinds present in the graph, sorted."""
        return [r[0] for r in self.conn.execute("SELECT DISTINCT kind FROM edges ORDER BY kind").fetchall()]

    def overview(
        self,
        group_by: str = "directory",
        expanded: list[str] | tuple[str, ...] = (),
        kinds: list[str] | None = None,
        externals: bool = True,
    ) -> dict:
        """Groups and derived Aggregate edges (ADR 0001: never stored).

        `group_by` picks a grouping strategy from `_GROUPINGS`; a strategy returns a
        `_Grouping` (a Group tree plus the Group each node is placed in), and the rest
        of this method is strategy-independent. Collapsed Groups are leaves; Groups in
        `expanded` show their child Groups, and expanded leaf-level Groups show their
        member nodes. Aggregate edges connect the visible items: one per directed pair,
        `kinds` = per-kind counts. `contains` is never aggregated; `kinds` (default all
        others) filters which edge kinds are counted. Returns
        {"groups", "nodes", "edges", "truncated", "total"}: `groups` are the visible Groups
        (with `parent`, `expanded`, `member_count`), `nodes` the members of expanded
        Groups (with `parent`), `edges` {id, source_id, target_id, kinds, count}.
        """
        try:
            strategy = self._GROUPINGS[group_by]
        except KeyError:
            raise ValueError(f"unknown group_by {group_by!r}; expected one of {sorted(self._GROUPINGS)}")
        grouping = getattr(self, strategy)(externals)
        groups = grouping.groups

        open_groups = set(expanded)

        def collapsed_at(group_id: str) -> str | None:
            """The outermost collapsed Group on the chain to `group_id` (None: all open)."""
            chain = []
            gid = group_id
            while gid is not None:
                chain.append(gid)
                gid = groups[gid]["parent"]
            return next((g for g in reversed(chain) if g not in open_groups), None)

        def visible_item(node_id: str) -> str | None:
            """Id of what stands for a node in the current view (a Group or the node)."""
            gid = grouping.placement.get(node_id)
            if gid is None:
                return None
            return collapsed_at(gid) or (gid if groups[gid]["node_id"] == node_id else node_id)

        edge_sql, params = "SELECT source_id, target_id, kind FROM edges WHERE kind <> 'contains'", []
        wanted = [k for k in (kinds or []) if k != "contains"]
        if kinds is not None:
            edge_sql += f" AND kind IN (SELECT unnest(?))"
            params.append(wanted)
        counts: dict[tuple[str, str], dict[str, int]] = {}
        for s, t, kind in self.conn.execute(edge_sql, params).fetchall():
            a, b = visible_item(s), visible_item(t)
            if a is None or b is None or a == b:
                continue
            per_kind = counts.setdefault((a, b), {})
            per_kind[kind] = per_kind.get(kind, 0) + 1
        edges = [
            {"id": f"agg:{a}>{b}", "source_id": a, "target_id": b,
             "kinds": dict(sorted(k.items())), "count": sum(k.values())}
            for (a, b), k in sorted(counts.items())
        ]

        def shown(g: dict) -> bool:
            return g["parent"] is None or (g["parent"] in open_groups and shown(groups[g["parent"]]))

        out_groups = sorted(
            ({**g, "expanded": g["id"] in open_groups, "member_count": grouping.sizes[g["id"]]}
             for g in groups.values() if shown(g)),
            key=lambda g: (g["parent"] or "", g["kind"], g["name"], g["id"]),
        )
        shown_open = [g["id"] for g in out_groups if g["expanded"]]
        members = self._fetchall(
            "SELECT * FROM nodes WHERE id IN (SELECT unnest(?))",
            [[n for n, gid in grouping.placement.items()
              if gid in shown_open and groups[gid]["node_id"] != n]],
        )
        for m in members:
            m["parent"] = grouping.placement[m["id"]]
        members.sort(key=lambda m: (m["parent"], m["line_start"] or 0, m["name"], m["id"]))
        return {"groups": out_groups, "nodes": members, "edges": edges,
                "truncated": False, "total": len(out_groups) + len(members)}

    _GROUPINGS = {"directory": "_directory_grouping"}

    def _directory_grouping(self, externals: bool) -> "_Grouping":
        """Directories (derived, id `dir:<abs path>`) > files > member nodes.

        The common ancestor of all indexed files is the invisible root. Nodes without a
        `file_path` (External placeholders) go in one `external` Group when `externals`.
        """
        rows = self._fetchall(
            "SELECT id, kind, name, qualified_name, file_path FROM nodes")
        files = {r["file_path"]: r for r in rows if r["kind"] == "file" and r["file_path"]}
        dirs = [os.path.dirname(p) for p in files]
        root = os.path.commonpath(dirs) if dirs else None
        groups: dict[str, dict] = {}

        def dir_group(path: str) -> str | None:
            if path == root or not path:
                return None
            gid = f"dir:{path}"
            if gid not in groups:
                groups[gid] = {"id": gid, "kind": "directory", "name": os.path.basename(path),
                               "qualified_name": path, "file_path": path, "node_id": None,
                               "parent": dir_group(os.path.dirname(path))}
            return gid

        for path, f in files.items():
            groups[f["id"]] = {"id": f["id"], "kind": "file", "name": f["name"],
                               "qualified_name": f["qualified_name"], "file_path": path,
                               "node_id": f["id"], "parent": dir_group(os.path.dirname(path))}
        placement: dict[str, str] = {}
        for r in rows:
            f = files.get(r["file_path"]) if r["file_path"] else None
            if f is not None:
                placement[r["id"]] = f["id"]
            elif externals and r["kind"] != "file":
                if "external" not in groups:
                    groups["external"] = {"id": "external", "kind": "external", "name": "external",
                                          "qualified_name": None, "file_path": None,
                                          "node_id": None, "parent": None}
                placement[r["id"]] = "external"
        return _Grouping(groups, placement)

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
