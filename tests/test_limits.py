"""Bounded work and robustness: budgets applied during traversal, hierarchy truncation, Overview caps,
absolute-path hygiene and deterministic name resolution. Graphs are hand-built via the mutation API."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.indexer import Indexer
from codegraph.query import Graph
from codegraph.vis.app import create_app


def build(tmp_path, populate):
    db = tmp_path / "g.duckdb"
    idx = Indexer(db)
    ids = populate(idx)
    idx.close()
    return db, ids


def fn(idx, name, path=None, kind="function", language="cpp", qualified_name=None):
    return idx.add_node(kind, name, language, qualified_name=qualified_name or name,
                        file_path=path or f"/r/{name}.cpp")


# ── neighborhood / reach apply the budget during the BFS ─────────────────────────────

def chain_db(tmp_path):
    def populate(idx):
        ids = [fn(idx, f"n{i}") for i in range(6)]
        for a, b in zip(ids, ids[1:]):
            idx.add_edge("calls", a, b)
        return ids
    return build(tmp_path, populate)


def test_neighborhood_stops_expanding_once_the_budget_is_hit_and_total_is_a_lower_bound(tmp_path):
    db, ids = chain_db(tmp_path)
    g = Graph(db)
    r = g.neighborhood(ids[0], direction="out", depth=5, limit=2)
    assert [n["name"] for n in r["nodes"]] == ["n0", "n1"]
    # n2 was discovered (the ring after the budget filled) but n3..n5 were never walked
    assert r["truncated"] is True and r["total"] == 3
    full = g.neighborhood(ids[0], direction="out", depth=5)
    assert full["total"] == 6 and full["truncated"] is False


def test_reach_limit_bounds_the_walk_and_keeps_shallow_rings(tmp_path):
    db, ids = chain_db(tmp_path)
    r = Graph(db).reach(ids[0], mode="dependencies", depth=5, limit=3)
    assert [n["name"] for n in r["nodes"]] == ["n0", "n1", "n2"]
    assert r["truncated"] is True and r["total"] > 3
    assert r["ring_counts"][1] == 1


# ── hierarchy truncation drops the deepest ring first ────────────────────────────────

@pytest.fixture
def tree(tmp_path):
    """root <- c0..c3 (children); the grandchildren hang off c3 and sort before every child by name."""
    def populate(idx):
        root = fn(idx, "root", kind="class")
        kids = [fn(idx, f"c{i}", kind="class") for i in range(4)]
        grand = [fn(idx, f"a_gc{i}", kind="class") for i in range(3)]
        for k in kids:
            idx.add_edge("inherits", k, root)
        for gc in grand:
            idx.add_edge("inherits", gc, kids[3])
        return {"root": root, "kids": kids, "grand": grand}
    db, ids = build(tmp_path, populate)
    with TestClient(create_app(db)) as c:
        c.ids = ids
        yield c


def test_hierarchy_truncation_drops_the_deepest_ring_first(tree):
    body = tree.get(f"/api/hierarchy/{tree.ids['root']}", params={"mode": "type", "limit": 5}).json()
    names = [n["name"] for n in body["nodes"]]
    assert names == ["root", "c0", "c1", "c2", "c3"]  # not the name-sorted a_gc* nodes
    assert body["truncated"] is True and body["total"] > 5  # total is a lower bound once truncated


def test_hierarchy_reports_ring_counts_and_edges_among_kept_nodes(tree):
    body = tree.get(f"/api/hierarchy/{tree.ids['root']}", params={"mode": "type"}).json()
    assert body["ring_counts"] == {"1": 4, "2": 3}
    assert body["truncated"] is False and body["total"] == 8
    assert len(body["edges"]) == 7


# ── Overview: member cap, expanded bound, relative ids ───────────────────────────────

@pytest.fixture
def wide(tmp_path):
    """/r/pkg/big.cpp holds 12 functions; /r/other/o.cpp holds one that calls into big."""
    def populate(idx):
        ids = {"big": idx.add_node("file", "big.cpp", "cpp", qualified_name="/r/pkg/big.cpp",
                                   file_path="/r/pkg/big.cpp"),
               "o": idx.add_node("file", "o.cpp", "cpp", qualified_name="/r/other/o.cpp",
                                 file_path="/r/other/o.cpp")}
        for i in range(12):
            ids[f"f{i:02d}"] = idx.add_node("function", f"f{i:02d}", "cpp", qualified_name=f"f{i:02d}",
                                            file_path="/r/pkg/big.cpp", line_start=i + 1)
            idx.add_edge("contains", ids["big"], ids[f"f{i:02d}"])
        ids["g"] = idx.add_node("function", "g", "cpp", qualified_name="g", file_path="/r/other/o.cpp")
        idx.add_edge("contains", ids["o"], ids["g"])
        for i in (0, 11):
            idx.add_edge("calls", ids["g"], ids[f"f{i:02d}"])
        return ids
    db, ids = build(tmp_path, populate)
    g = Graph(db)
    g.ids = ids
    yield g, db
    g.close()


def test_directory_group_ids_are_root_relative_never_absolute(wide):
    g, _ = wide
    ids = {x["id"] for x in g.overview()["groups"]}
    assert {"dir:pkg", "dir:other"} == ids - {g.ids["big"], g.ids["o"]}
    assert not any("/r" in i for i in ids)


def test_expanding_a_group_caps_members_and_reports_truncation(wide):
    g, _ = wide
    r = g.overview(expanded=["dir:pkg", g.ids["big"]], member_limit=5, kinds=["calls"])
    assert [m["name"] for m in r["nodes"]] == ["f00", "f01", "f02", "f03", "f04"]
    assert r["truncated"] is True
    assert r["total"] == len(r["groups"]) + 12
    shown = {x["id"] for x in r["groups"]} | {m["id"] for m in r["nodes"]}
    assert all(e["source_id"] in shown and e["target_id"] in shown for e in r["edges"])  # no dangling edges
    full = g.overview(expanded=["dir:pkg", g.ids["big"]], member_limit=50)
    assert full["truncated"] is False and len(full["nodes"]) == 12


def test_overview_endpoint_caps_members_with_limit_and_bounds_expanded(wide):
    g, db = wide
    g.close()  # the app opens its own read-only connection
    with TestClient(create_app(db)) as c:
        r = c.get("/api/overview", params={"expanded": ["dir:pkg", g.ids["big"]], "limit": 4}).json()
        assert r["truncated"] is True
        assert sum(1 for n in r["nodes"] if not n["group"]) == 4
        assert c.get("/api/overview", params={"limit": 501}).status_code == 422
        too_many = c.get("/api/overview", params={"expanded": [f"dir:x{i}" for i in range(51)]})
        assert too_many.status_code == 422
        assert c.get("/api/overview", params={"expanded": [f"dir:x{i}" for i in range(50)]}).status_code == 200
        ids = [n["id"] for n in c.get("/api/overview").json()["nodes"]]
        assert not any("/r" in i for i in ids)


# ── paths and name resolution ────────────────────────────────────────────────────────

def test_a_directory_named_dot_dot_foo_is_not_mistaken_for_a_parent_path(tmp_path):
    def populate(idx):
        return {"a": idx.add_node("file", "a.c", "c", qualified_name="/r/..foo/a.c", file_path="/r/..foo/a.c"),
                "b": idx.add_node("file", "b.c", "c", qualified_name="/r/bar/b.c", file_path="/r/bar/b.c")}
    db, ids = build(tmp_path, populate)
    with TestClient(create_app(db)) as c:
        body = c.get(f"/api/node/{ids['a']}").json()
    assert body["path"] == "..foo/a.c" and body["qualified_name"] == "..foo/a.c"


def test_ambiguous_qualified_names_resolve_deterministically_by_kind_priority_then_id(tmp_path):
    def populate(idx):
        # same qualified name, three nodes: a variable, a function and a class
        return {k: idx.add_node(k, "Dup", "cpp", qualified_name="Dup", file_path=f"/r/{k}.cpp")
                for k in ("variable", "function", "class")}
    db, ids = build(tmp_path, populate)
    g = Graph(db)
    for _ in range(3):
        assert g.resolve_node("Dup")["id"] == ids["class"]  # class outranks function outranks variable
    g.close()  # the app opens its own read-only connection
    with TestClient(create_app(db)) as c:
        assert c.get("/api/neighborhood/Dup").json()["focus"] == ids["class"]
