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


# Direction -> (owner column, neighbor column): 'out' follows source to target, 'in' the reverse.
_DIRECTION_COLS = {"out": ("source_id", "target_id"), "in": ("target_id", "source_id")}


def stub_id(owner: str, direction: str, kind: str) -> str:
    """Id of the Stub node standing for an owner's hidden neighbors of one kind and direction."""
    return f"stub:{owner}:{direction}:{kind}"


def _sort_key(row: dict) -> tuple[str, str]:
    """Order among nodes of equal depth: qualified name (else name), then id."""
    return (row["qualified_name"] or row["name"], row["id"])


def _ring_key(row: dict) -> tuple:
    return (row["depth"], *_sort_key(row))


def _truncate(rows: list[dict], limit: int | None) -> tuple[list[dict], bool]:
    """The first `limit` rows (None: all) and whether any were dropped."""
    if limit is None or len(rows) <= limit:
        return rows, False
    return rows[:limit], True


class _Grouping:
    """What an overview grouping strategy returns.

    groups:    {group id: {id, kind, name, qualified_name, file_path, node_id, parent}};
               `node_id` is the real node a Group is (a file, a package), else None.
    group_of:  {node id: id of the innermost Group it belongs to}; a Group's own node is
               placed in that Group. Nodes absent from `group_of` are not shown.
    member_counts: {group id: nodes placed in the Group or any descendant}.
    """

    def __init__(self, groups: dict[str, dict], group_of: dict[str, str]):
        self.groups = groups
        self.group_of = group_of
        self.member_counts = {gid: 0 for gid in groups}
        for gid in group_of.values():
            while gid is not None:
                self.member_counts[gid] += 1
                gid = groups[gid]["parent"]


class Graph:
    """Read-only query interface over an indexed codegraph database."""

    def __init__(self, db_path: str | Path | None = None, read_only: bool = False, *,
                 conn: duckdb.DuckDBPyConnection | None = None):
        """Open `db_path`, or wrap an already open connection `conn` (see `cursor`)."""
        self.conn = conn if conn is not None else connect(db_path, read_only=read_only)

    def cursor(self) -> "Graph":
        """A Graph on a new cursor of this connection, for use in one thread/request."""
        return Graph(conn=self.conn.cursor())

    @staticmethod
    def _kind_clause(kinds: list[str] | None, column: str = "e.kind") -> tuple[str, list]:
        """SQL fragment and params restricting `column` to `kinds` (empty/None: no restriction)."""
        if not kinds:
            return "", []
        return f"AND {column} IN ({', '.join('?' * len(kinds))})", list(kinds)

    def common_root(self) -> str | None:
        """Deepest directory containing every indexed file, or None (no files, or a mix of
        absolute and relative paths). The one definition of the root that Overview Group
        ids and the vis layer's relative display paths are measured from.
        """
        dirs = [os.path.dirname(r[0]) for r in self.conn.execute(
            "SELECT DISTINCT file_path FROM nodes WHERE kind = 'file' AND file_path IS NOT NULL").fetchall()]
        if not dirs:
            return None
        try:
            return os.path.commonpath(dirs)
        except ValueError:
            return None

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
        """The node with this qualified name. Several nodes can share one (a class and a
        constructor function, nodes of different languages); the winner is deterministic:
        highest SEARCH_KIND_PRIORITY kind (class, type, function, ...), then language, then id.
        """
        rows = self._fetchall(
            f"SELECT * FROM nodes WHERE qualified_name = ? "
            f"ORDER BY {self._kind_rank_sql('kind')}, language, id LIMIT 1", [qualified_name])
        return rows[0] if rows else None

    def node_by_name(self, name: str) -> list[dict]:
        return self._fetchall(
            "SELECT * FROM nodes WHERE qualified_name = ? OR name = ?", [name, name]
        )

    # ── Edge queries ──────────────────────────────────────────────────────────

    def edges_from(self, node_id: str, kinds: list[str] | None = None) -> list[dict]:
        kind_sql, kind_params = self._kind_clause(kinds, "kind")
        return self._fetchall(f"SELECT * FROM edges WHERE source_id = ? {kind_sql}", [node_id, *kind_params])

    def edges_to(self, node_id: str, kinds: list[str] | None = None) -> list[dict]:
        kind_sql, kind_params = self._kind_clause(kinds, "kind")
        return self._fetchall(f"SELECT * FROM edges WHERE target_id = ? {kind_sql}", [node_id, *kind_params])

    # ── Traversal ─────────────────────────────────────────────────────────────

    def traverse(
        self,
        node_id: str,
        edge_kinds: list[str] | None = None,
        direction: str = "out",
        max_depth: int = 1,
    ) -> list[dict]:
        """BFS via DuckDB recursive CTE. direction='out' follows source→target; 'in' reverses."""
        join_col, reach_col = _DIRECTION_COLS[direction]
        kind_filter, kind_params = self._kind_clause(edge_kinds)

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

    def _ranked_groups(
        self, owners: list[str], steps: list[tuple[str, str, str]], kind_sql: str, kind_params: list
    ) -> dict[tuple[str, str, str], list[tuple[str, str]]]:
        """Distinct neighbors of each owner per (owner, direction, edge kind) as (sort key, id), sorted.

        `steps` is a list of (direction, owner column, neighbor column). Self-loops are ignored.
        """
        groups: dict[tuple[str, str, str], set[tuple[str, str]]] = {}
        for direction, own_col, nb_col in steps:
            rows = self.conn.execute(
                f"SELECT DISTINCT e.{own_col}, e.kind, e.{nb_col}, COALESCE(NULLIF(n.qualified_name, ''), n.name) "
                f"FROM edges e JOIN nodes n ON n.id = e.{nb_col} "
                f"WHERE e.{own_col} IN (SELECT unnest(?)) AND e.{nb_col} <> e.{own_col} {kind_sql}",
                [owners, *kind_params],
            ).fetchall()
            for owner, kind, nb, key in rows:
                groups.setdefault((owner, direction, kind), set()).add((key, nb))
        return {g: sorted(v) for g, v in groups.items()}

    @staticmethod
    def _steps(direction: str) -> list[tuple[str, str, str]]:
        """(direction, owner column, neighbor column) steps for 'out', 'in' or 'both'."""
        directions = ["out", "in"] if direction == "both" else [direction]
        return [(d, *_DIRECTION_COLS[d]) for d in directions]

    def _walk(self, node_id: str, direction: str, depth: int, edge_kinds: list[str] | None,
              limit: int | None, per_node_cap: int | None) -> dict:
        """Breadth-first walk with the node budget applied as it goes.

        Rings are filled in order and the walk stops as soon as a ring does not fit the
        budget `limit` (the focus counts): the ring that overflows keeps its first nodes
        by qualified name and nothing deeper is queried, so the work is bounded by the
        budget rather than by the size of the graph. Returns {"depth_of": {id: ring},
        "stubs", "ring_counts": {ring: nodes discovered}, "truncated", "total"}. `total`
        counts every node discovered: exact when not truncated, otherwise a lower bound
        (the rings beyond the one that overflowed were never walked).
        """
        kind_sql, kind_params = self._kind_clause(edge_kinds)
        steps = self._steps(direction)
        depth_of: dict[str, int] = {node_id: 0}
        stubs: list[dict] = []
        ring_counts: dict[int, int] = {}
        total, truncated = 1, False
        frontier = [node_id]
        for d in range(1, depth + 1):
            if not frontier:
                break
            found: dict[str, str] = {}
            for (owner, dirn, kind), nbs in sorted(self._ranked_groups(frontier, steps, kind_sql, kind_params).items()):
                if per_node_cap is not None and len(nbs) > per_node_cap:
                    stubs.append({"id": stub_id(owner, dirn, kind), "owner": owner, "direction": dirn,
                                  "kind": kind, "hidden": len(nbs) - per_node_cap, "offset": per_node_cap})
                    nbs = nbs[:per_node_cap]
                found.update({i: key for key, i in nbs})
            ring = sorted((key, i) for i, key in found.items() if i not in depth_of)
            if ring:
                ring_counts[d] = len(ring)
                total += len(ring)
            if limit is not None and len(ring) > limit - len(depth_of):
                ring, truncated = ring[:max(0, limit - len(depth_of))], True
            for _, i in ring:
                depth_of[i] = d
            if truncated:
                break
            frontier = [i for _, i in ring]
        return {"depth_of": depth_of, "stubs": stubs, "ring_counts": ring_counts,
                "truncated": truncated, "total": total}

    def _nodes_at(self, depth_of: dict[str, int]) -> list[dict]:
        """Node rows for {id: ring}, each with `depth`, ordered ring by ring then by name."""
        rows = self._fetchall("SELECT * FROM nodes WHERE id IN (SELECT unnest(?))", [list(depth_of)])
        for r in rows:
            r["depth"] = depth_of[r["id"]]
        rows.sort(key=_ring_key)
        return rows

    def neighborhood(
        self,
        node_id: str,
        direction: str = "both",
        depth: int = 1,
        edge_kinds: list[str] | None = None,
        limit: int | None = None,
        per_node_cap: int | None = None,
    ) -> dict | None:
        """Nodes within `depth` of a Focus node, plus every edge among the included nodes.

        direction: 'out' (source to target), 'in' (reverse) or 'both'. Each returned
        node is a node dict with an added `depth` (0 for the focus). `limit` caps the
        node count, applied during the walk (see `_walk`): the deepest BFS ring is dropped
        first (a ring that only partly fits keeps its first nodes by qualified name).
        `per_node_cap` caps the neighbors followed per node, edge kind and direction
        (first by qualified name); each overflowing group yields a Stub node record
        {"id", "owner", "direction", "kind", "hidden", "offset"} where `offset` is the
        number of neighbors already shown (page the rest in with `neighbors_page`).
        Returns {"nodes", "edges", "stubs", "truncated", "total"} where `total` is the
        node count found: exact unless truncated, then a lower bound. None if the focus
        node does not exist.
        """
        if self.node_by_id(node_id) is None:
            return None
        w = self._walk(node_id, direction, depth, edge_kinds, limit, per_node_cap)
        rows = self._nodes_at(w["depth_of"])
        kept = {r["id"] for r in rows}
        return {"nodes": rows, "edges": self.edges_among(list(kept), edge_kinds),
                "stubs": [s for s in w["stubs"] if s["owner"] in kept],
                "truncated": w["truncated"], "total": w["total"]}

    def neighbors_page(
        self, node_id: str, direction: str, kind: str, offset: int = 0, limit: int = 15
    ) -> dict | None:
        """One page of a node's neighbors for a single edge kind and direction ('in' or 'out').

        Neighbors are ordered as in `neighborhood` (by qualified name), so a Stub node's
        `offset` continues exactly where the capped view stopped. Returns
        {"nodes", "edges", "total", "hidden"}: nodes carry depth 1, edges are those between
        the owner and the page, `total` counts all neighbors in the group and `hidden`
        those still unseen after this page. None if the node does not exist.
        """
        if self.node_by_id(node_id) is None:
            return None
        groups = self._ranked_groups([node_id], self._steps(direction), "AND e.kind = ?", [kind])
        nbs = [i for _, i in groups.get((node_id, direction, kind), [])]
        page = nbs[offset:offset + limit]
        position = {i: n for n, i in enumerate(page)}
        nodes = self._fetchall("SELECT * FROM nodes WHERE id IN (SELECT unnest(?))", [page])
        for n in nodes:
            n["depth"] = 1
        nodes.sort(key=lambda n: position[n["id"]])
        own, other = _DIRECTION_COLS[direction]
        edges = self._fetchall(
            f"SELECT * FROM edges e WHERE e.{own} = ? AND e.{other} IN (SELECT unnest(?)) "
            f"AND e.kind = ? ORDER BY e.id",
            [node_id, page, kind],
        )
        return {"nodes": nodes, "edges": edges, "total": len(nbs),
                "hidden": max(0, len(nbs) - offset - len(page))}

    # Tie-break order among equally good matches: types and functions before containers and members.
    SEARCH_KIND_PRIORITY = ("class", "type", "function", "method", "package", "module",
                            "file", "variable", "field")

    @classmethod
    def _kind_rank_sql(cls, column: str) -> str:
        """SQL CASE ranking a node kind by SEARCH_KIND_PRIORITY (unknown kinds last)."""
        return f"CASE {column} " + " ".join(
            f"WHEN '{k}' THEN {i}" for i, k in enumerate(cls.SEARCH_KIND_PRIORITY)
        ) + f" ELSE {len(cls.SEARCH_KIND_PRIORITY)} END"

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
        qname = "(CASE WHEN n.kind = 'file' THEN NULL ELSE lower(n.qualified_name) END)"
        name = "lower(n.name)"
        path = "lower(n.file_path)"
        sub = f"({name} LIKE ? ESCAPE '\\' OR {qname} LIKE ? ESCAPE '\\')"
        path_sql = f" OR {path} LIKE ? ESCAPE '\\'" if by_path else ""
        where = [f"({sub}{path_sql})"]
        params: list[Any] = [like_any, like_any] + ([like_any] if by_path else [])
        for col, vals in (("n.kind", kinds), ("n.language", languages)):
            if vals:
                where.append(f"{col} IN ({', '.join('?' * len(vals))})")
                params += list(vals)
        where_sql = " AND ".join(where)
        total = self.conn.execute(f"SELECT COUNT(*) FROM nodes n WHERE {where_sql}", params).fetchone()[0]
        match_rank = (f"CASE WHEN {name} = ? OR {qname} = ? THEN 0 "
                      f"WHEN {name} LIKE ? ESCAPE '\\' OR {qname} LIKE ? ESCAPE '\\' THEN 1 "
                      f"WHEN {sub} THEN 2 ELSE 3 END")
        rank_params = [q, q, like_prefix, like_prefix, like_any, like_any]
        rows = self._fetchall(
            f"SELECT n.*, "
            f"(SELECT COUNT(*) FROM edges e WHERE e.source_id = n.id OR e.target_id = n.id) AS degree, "
            f"(SELECT COUNT(DISTINCT e.source_id) FROM edges e JOIN nodes f ON f.id = e.source_id "
            f" WHERE e.target_id = n.id AND e.kind = 'contains' AND f.kind = 'file') AS file_count, "
            f"{match_rank} AS match_rank "
            f"FROM nodes n WHERE {where_sql} "
            f"ORDER BY match_rank, {self._kind_rank_sql('n.kind')}, degree DESC, lower(n.qualified_name), n.id LIMIT ?",
            rank_params + params + [limit],
        )
        for r in rows:
            del r["match_rank"]
        return {"nodes": rows, "total": total, "truncated": total > len(rows)}

    def edges_among(self, node_ids: list[str], edge_kinds: list[str] | None = None) -> list[dict]:
        """Every edge whose source and target are both in `node_ids` (optionally of the given kinds)."""
        kind_sql, kind_params = self._kind_clause(edge_kinds)
        return self._fetchall(
            f"SELECT * FROM edges e WHERE e.source_id IN (SELECT unnest(?)) "
            f"AND e.target_id IN (SELECT unnest(?)) {kind_sql} ORDER BY e.id",
            [node_ids, node_ids, *kind_params],
        )

    def _union_walk(self, node_id: str, directions: list[str], edge_kinds: list[str],
                    depth: int, limit: int | None, per_node_cap: int | None) -> dict | None:
        """Walk each direction independently, merge (keeping the smaller depth) and truncate.

        Result shape of `neighborhood` plus `ring_counts` {depth: nodes found} for depth >= 1:
        exact when not truncated, otherwise a lower bound (see `_walk`). Directions are
        expanded independently (callers of callees are not included). None if the node
        does not exist.
        """
        if self.node_by_id(node_id) is None:
            return None
        walks = [self._walk(node_id, d, depth, edge_kinds, limit, per_node_cap) for d in directions]
        depth_of: dict[str, int] = {}
        for w in walks:
            for i, d in w["depth_of"].items():
                depth_of[i] = min(d, depth_of.get(i, d))
        rows = self._nodes_at(depth_of)
        found = len(rows)
        rows, trimmed = _truncate(rows, limit)
        any_cut = any(w["truncated"] for w in walks)
        if any_cut:  # rings come from the walks (the dropped nodes were counted there); overlaps keep the max
            ring_counts: dict[int, int] = {}
            for w in walks:
                for d, c in w["ring_counts"].items():
                    ring_counts[d] = max(ring_counts.get(d, 0), c)
        else:
            ring_counts = {}
            for r in rows:
                if r["depth"] >= 1:
                    ring_counts[r["depth"]] = ring_counts.get(r["depth"], 0) + 1
        kept = {r["id"] for r in rows}
        stubs = {s["id"]: s for w in walks for s in w["stubs"] if s["owner"] in kept}
        return {
            "nodes": rows, "edges": self.edges_among(list(kept), edge_kinds),
            "stubs": sorted(stubs.values(), key=lambda s: s["id"]),
            "truncated": trimmed or any_cut,
            "total": max([found, *(w["total"] for w in walks)]),
            "ring_counts": dict(sorted(ring_counts.items())),
        }

    # Edge kinds that carry impact. All point from dependant to dependency (a calls b, a
    # inherits b), so the Impact set follows them backwards (for inherits: descendants)
    # and Dependencies follow them forwards (for inherits: ancestors).
    REACH_KINDS = ["calls", "references", "instantiates", "inherits"]

    def reach(self, node_id: str, mode: str = "both", depth: int = 2,
              limit: int | None = None, per_node_cap: int | None = None) -> dict | None:
        """The Impact set ('impact'), the Dependencies ('dependencies') or their union ('both').

        Same result shape as `neighborhood`, plus `ring_counts` (see `_union_walk`).
        """
        directions = {"impact": ["in"], "dependencies": ["out"], "both": ["in", "out"]}[mode]
        return self._union_walk(node_id, directions, self.REACH_KINDS, depth, limit, per_node_cap)

    # Hierarchy views: the edge kinds and directions each mode follows from the Focus node. Type mode
    # is ancestors plus descendants (never siblings); declaration mode is the contained members.
    HIERARCHY_MODES = {"type": (["in", "out"], ["inherits"]), "declaration": (["out"], ["contains", "defines"])}

    def hierarchy(self, node_id: str, mode: str, limit: int | None = None) -> dict | None:
        """The type or declaration hierarchy around a node, truncated deepest ring first.

        Result shape of `reach` (nodes carry `depth`; the focus is depth 0). `limit` is
        applied during the walk, so a big hierarchy costs no more than its budget.
        """
        directions, kinds = self.HIERARCHY_MODES[mode]
        return self._union_walk(node_id, directions, kinds, depth=1_000_000, limit=limit, per_node_cap=None)

    def neighbor_counts(self, node_id: str) -> dict[str, dict[str, int]]:
        """Distinct neighbor nodes per edge kind, split by direction: {"in": {...}, "out": {...}}."""
        out: dict[str, dict[str, int]] = {"in": {}, "out": {}}
        for direction, (own, other) in _DIRECTION_COLS.items():
            for kind, count in self.conn.execute(
                f"SELECT kind, COUNT(DISTINCT {other}) FROM edges WHERE {own} = ? "
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
        member_limit: int | None = None,
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

        `member_limit` caps the member nodes returned (first by Group, line, name); Groups
        themselves are never capped. `truncated` says members were dropped, `total` counts
        every visible Group and member, and Aggregate edges to dropped members are omitted.
        """
        try:
            strategy = self._GROUPINGS[group_by]
        except KeyError:
            raise ValueError(f"unknown group_by {group_by!r}; expected one of {sorted(self._GROUPINGS)}")
        grouping = strategy(self, externals)
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
            gid = grouping.group_of.get(node_id)
            if gid is None:
                return None
            return collapsed_at(gid) or (gid if groups[gid]["node_id"] == node_id else node_id)

        edge_sql, params = "SELECT source_id, target_id, kind FROM edges WHERE kind <> 'contains'", []
        if kinds is not None:
            edge_sql += " AND kind IN (SELECT unnest(?))"
            params.append([k for k in kinds if k != "contains"])
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
            ({**g, "expanded": g["id"] in open_groups, "member_count": grouping.member_counts[g["id"]]}
             for g in groups.values() if shown(g)),
            key=lambda g: (g["parent"] or "", g["kind"], g["name"], g["id"]),
        )
        shown_open = [g["id"] for g in out_groups if g["expanded"]]
        open_shown = set(shown_open)
        member_ids = [(n, gid) for n, gid in grouping.group_of.items()
                      if gid in open_shown and groups[gid]["node_id"] != n]
        truncated = member_limit is not None and len(member_ids) > member_limit
        members = self._fetchall(
            "SELECT n.*, p.parent FROM nodes n "
            "JOIN (SELECT unnest(?) AS id, unnest(?) AS parent) p ON p.id = n.id "
            "ORDER BY p.parent, COALESCE(n.line_start, 0), n.name, n.id"
            + (" LIMIT ?" if truncated else ""),
            [[n for n, _ in member_ids], [gid for _, gid in member_ids]] + ([member_limit] if truncated else []),
        )
        if truncated:  # edges to members that were cut have nothing to attach to
            shown_items = {g["id"] for g in out_groups} | {m["id"] for m in members}
            edges = [e for e in edges if e["source_id"] in shown_items and e["target_id"] in shown_items]
        return {"groups": out_groups, "nodes": members, "edges": edges,
                "truncated": truncated, "total": len(out_groups) + len(member_ids)}

    @staticmethod
    def _external_group(groups: dict[str, dict]) -> str:
        """The single `external` Group (created on first use); shared by every grouping."""
        groups.setdefault("external", {"id": "external", "kind": "external", "name": "external",
                                       "qualified_name": None, "file_path": None,
                                       "node_id": None, "parent": None})
        return "external"

    def _directory_grouping(self, externals: bool) -> "_Grouping":
        """Directories (derived, id `dir:<path relative to the root>`) > files > member nodes.

        The common ancestor of all indexed files (`common_root`) is the invisible root; ids
        are relative to it so they never expose a server path. Nodes without a `file_path`
        (External placeholders) go in one `external` Group when `externals`.
        """
        rows = self._fetchall(
            "SELECT id, kind, name, qualified_name, file_path FROM nodes")
        files = {r["file_path"]: r for r in rows if r["kind"] == "file" and r["file_path"]}
        root = self.common_root()
        groups: dict[str, dict] = {}

        def dir_group(path: str) -> str | None:
            if path == root or not path:
                return None
            gid = "dir:" + (os.path.relpath(path, root).replace(os.sep, "/") if root else path)
            if gid not in groups:
                groups[gid] = {"id": gid, "kind": "directory", "name": os.path.basename(path),
                               "qualified_name": path, "file_path": path, "node_id": None,
                               "parent": dir_group(os.path.dirname(path))}
            return gid

        for path, f in files.items():
            groups[f["id"]] = {"id": f["id"], "kind": "file", "name": f["name"],
                               "qualified_name": f["qualified_name"], "file_path": path,
                               "node_id": f["id"], "parent": dir_group(os.path.dirname(path))}
        group_of: dict[str, str] = {}
        for r in rows:
            f = files.get(r["file_path"]) if r["file_path"] else None
            if f is not None:
                group_of[r["id"]] = f["id"]
            elif externals and r["kind"] != "file":
                group_of[r["id"]] = self._external_group(groups)
        return _Grouping(groups, group_of)

    def _package_grouping(self, externals: bool) -> "_Grouping":
        """Packages (nested via `contains`) are the Groups; anything outside a Package is
        grouped by its file (C and C++ have no Package nodes, so files are the Groups).

        Mixed repos: a node goes in its innermost containing Package, else in its file's
        Group. A file node goes in the Package its file contains (so `imports` edges from
        an Ada file attach to that Package) unless the file also has nodes outside any
        Package, in which case it is their file Group. External placeholders (no
        `file_path`, including external Packages) go in one `external` Group when
        `externals`.
        """
        rows = self._fetchall("SELECT id, kind, name, qualified_name, file_path FROM nodes")
        by_id = {r["id"]: r for r in rows}
        children: dict[str, list[str]] = {}
        for p, c in self.conn.execute(
                "SELECT source_id, target_id FROM edges WHERE kind = 'contains'").fetchall():
            children.setdefault(p, []).append(c)
        pkgs = {r["id"]: r for r in rows if r["kind"] == "package" and r["file_path"]}
        files = {r["file_path"]: r for r in rows if r["kind"] == "file" and r["file_path"]}

        groups: dict[str, dict] = {
            pid: {"id": pid, "kind": "package", "name": r["name"],
                  "qualified_name": r["qualified_name"], "file_path": r["file_path"],
                  "node_id": pid, "parent": None}
            for pid, r in sorted(pkgs.items(), key=lambda kv: kv[1]["qualified_name"] or "")}
        group_of: dict[str, str] = {pid: pid for pid in pkgs}
        owner_file: dict[str, str] = {}  # file node id -> first top-level Package it contains
        for pid in groups:
            stack = list(children.get(pid, []))
            while stack:
                n = stack.pop()
                if n in group_of and n != pid:
                    if n in pkgs:  # nested Package: becomes a child Group, don't descend here
                        groups[n]["parent"] = pid
                    continue
                if n in by_id:
                    group_of[n] = pid
                    stack.extend(children.get(n, []))
        # a file node's Package: the Package it directly contains
        for r in files.values():
            fid = r["id"]
            top = [c for c in children.get(fid, []) if c in pkgs]
            if top:
                owner_file[fid] = min(top, key=lambda c: pkgs[c]["qualified_name"] or "")

        def file_group(path: str) -> str:
            f = files[path]
            groups.setdefault(f["id"], {"id": f["id"], "kind": "file", "name": f["name"],
                                        "qualified_name": f["qualified_name"], "file_path": path,
                                        "node_id": f["id"], "parent": None})
            return f["id"]

        for r in rows:
            nid = r["id"]
            if nid in group_of or r["kind"] == "file":
                continue
            if r["file_path"] in files:
                group_of[nid] = file_group(r["file_path"])
            elif externals:
                group_of[nid] = self._external_group(groups)
        for path, f in files.items():
            if f["id"] in groups:
                group_of[f["id"]] = f["id"]
            elif f["id"] in owner_file:
                group_of[f["id"]] = owner_file[f["id"]]
            else:
                group_of[f["id"]] = file_group(path)
        return _Grouping(groups, group_of)

    _GROUPINGS = {"directory": _directory_grouping, "package": _package_grouping}

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
