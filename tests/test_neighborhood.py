"""Graph.neighborhood and its sibling detail primitives, on small hand-built graphs."""
from __future__ import annotations
import pytest

from codegraph.indexer import Indexer
from codegraph.query import Graph


@pytest.fixture
def chain(tmp_path):
    """e -calls-> a -calls-> b -calls-> c -calls-> d;  a -inherits-> x;  a -calls-> c (shortcut)."""
    db = tmp_path / "chain.duckdb"
    idx = Indexer(db)
    ids = {n: idx.add_node("function", n, "cpp", qualified_name=n, file_path=f"/r/{n}.cpp") for n in "abcdex"}
    for s, t in ["ea", "ab", "bc", "cd", "ac"]:
        idx.add_edge("calls", ids[s], ids[t])
    idx.add_edge("inherits", ids["a"], ids["x"])
    idx.close()
    g = Graph(db)
    g.ids = ids
    yield g
    g.close()


def names(result):
    return {n["name"]: n["depth"] for n in result["nodes"]}


def test_depth_annotates_each_node_with_distance_from_focus(chain):
    r = chain.neighborhood(chain.ids["a"], direction="out", depth=2)
    assert names(r) == {"a": 0, "b": 1, "c": 1, "x": 1, "d": 2}
    assert r["truncated"] is False
    assert r["total"] == 5


def test_depth_one_stops_at_direct_neighbours(chain):
    r = chain.neighborhood(chain.ids["a"], direction="out", depth=1)
    assert names(r) == {"a": 0, "b": 1, "c": 1, "x": 1}


def test_direction_in_follows_edges_backwards(chain):
    r = chain.neighborhood(chain.ids["c"], direction="in", depth=2)
    assert names(r) == {"c": 0, "a": 1, "b": 1, "e": 2}


def test_direction_both_follows_either_way(chain):
    r = chain.neighborhood(chain.ids["b"], direction="both", depth=1)
    assert names(r) == {"b": 0, "a": 1, "c": 1}


def test_edge_kind_filter_restricts_traversal_and_returned_edges(chain):
    r = chain.neighborhood(chain.ids["a"], direction="out", depth=2, edge_kinds=["inherits"])
    assert names(r) == {"a": 0, "x": 1}
    assert {e["kind"] for e in r["edges"]} == {"inherits"}


def test_edges_include_every_edge_among_included_nodes(chain):
    # depth 1 from b (both): a and c are included; the a->c shortcut joins two neighbours and must be returned.
    r = chain.neighborhood(chain.ids["b"], direction="both", depth=1)
    pairs = {(e["source_id"], e["target_id"]) for e in r["edges"]}
    i = chain.ids
    assert pairs == {(i["a"], i["b"]), (i["b"], i["c"]), (i["a"], i["c"])}


def test_edges_to_excluded_nodes_are_dropped(chain):
    r = chain.neighborhood(chain.ids["a"], direction="out", depth=1)
    included = {n["id"] for n in r["nodes"]}
    assert all(e["source_id"] in included and e["target_id"] in included for e in r["edges"])


def test_limit_drops_deepest_ring_first_and_reports_total(chain):
    r = chain.neighborhood(chain.ids["a"], direction="out", depth=2, limit=4)
    assert names(r) == {"a": 0, "b": 1, "c": 1, "x": 1}
    assert r["truncated"] is True
    assert r["total"] == 5


def test_limit_inside_a_ring_keeps_a_deterministic_subset(chain):
    r = chain.neighborhood(chain.ids["a"], direction="out", depth=1, limit=3)
    assert len(r["nodes"]) == 3 and r["truncated"] is True and r["total"] == 4
    assert names(r) == names(chain.neighborhood(chain.ids["a"], direction="out", depth=1, limit=3))


def test_unknown_focus_returns_none(chain):
    assert chain.neighborhood("nope") is None


def test_neighbour_counts_are_distinct_neighbours_per_kind_and_direction(chain):
    counts = chain.neighbour_counts(chain.ids["a"])
    assert counts == {"in": {"calls": 1}, "out": {"calls": 2, "inherits": 1}}


def test_defining_files_lists_every_file_containing_the_node(tmp_path):
    db = tmp_path / "df.duckdb"
    idx = Indexer(db)
    f1 = idx.add_node("file", "a.ads", "ada", qualified_name="/r/a.ads", file_path="/r/a.ads")
    f2 = idx.add_node("file", "a.adb", "ada", qualified_name="/r/a.adb", file_path="/r/a.adb")
    p = idx.add_node("package", "Geo", "ada", qualified_name="Geo", file_path="/r/a.ads")
    idx.add_edge("contains", f1, p)
    idx.add_edge("contains", f2, p)
    idx.close()
    g = Graph(db)
    assert g.defining_files(p) == ["/r/a.adb", "/r/a.ads"]
