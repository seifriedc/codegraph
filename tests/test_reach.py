"""Graph.reach: Impact set / Dependencies / both, on a small hand-built graph."""

from __future__ import annotations
import pytest

from codegraph.indexer import Indexer
from codegraph.query import Graph


@pytest.fixture
def chain(tmp_path):
    """e -calls-> a -calls-> b -calls-> c -calls-> d;  a -calls-> c;  a -inherits-> x."""
    db = tmp_path / "chain.duckdb"
    idx = Indexer(db)
    ids = {
        n: idx.add_node("function", n, "cpp", qualified_name=n, file_path=f"/r/{n}.cpp")
        for n in "abcdex"
    }
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


def test_impact_follows_incoming_calls_transitively(chain):
    r = chain.reach(chain.ids["c"], mode="impact", depth=3)
    assert names(r) == {"c": 0, "b": 1, "a": 1, "e": 2}


def test_impact_over_inherits_means_descendants(chain):
    # a inherits x, so changing x impacts a (and a's callers); never the other way round.
    assert names(chain.reach(chain.ids["x"], mode="impact", depth=2)) == {"x": 0, "a": 1, "e": 2}
    assert names(chain.reach(chain.ids["a"], mode="impact", depth=2)) == {"a": 0, "e": 1}


def test_dependencies_follow_outgoing_edges_including_ancestors(chain):
    r = chain.reach(chain.ids["a"], mode="dependencies", depth=2)
    assert names(r) == {"a": 0, "b": 1, "c": 1, "x": 1, "d": 2}


def test_both_is_the_union_of_impact_and_dependencies(chain):
    r = chain.reach(chain.ids["b"], mode="both", depth=2)
    # impact: a(1), e(2); dependencies: c(1), d(2). Not a's other callee x.
    assert names(r) == {"b": 0, "a": 1, "c": 1, "e": 2, "d": 2}
    ids = chain.ids
    assert {(e["source_id"], e["target_id"]) for e in r["edges"]} == {
        (ids["e"], ids["a"]),
        (ids["a"], ids["b"]),
        (ids["b"], ids["c"]),
        (ids["c"], ids["d"]),
        (ids["a"], ids["c"]),
    }


def test_ring_counts_are_exact_up_to_the_ring_that_overflowed_the_limit(chain):
    # the walk stops at the ring that overflows the budget: it is counted in full (3), deeper
    # rings are never walked, so total (4) is a lower bound of the true 5
    r = chain.reach(chain.ids["a"], mode="dependencies", depth=2, limit=2)
    assert r["ring_counts"] == {1: 3}
    assert r["truncated"] is True and r["total"] == 4 and len(r["nodes"]) == 2
    full = chain.reach(chain.ids["a"], mode="dependencies", depth=2)
    assert full["ring_counts"] == {1: 3, 2: 1} and full["total"] == 5


def test_reach_of_unknown_node_is_none(chain):
    assert chain.reach("nope", mode="impact", depth=1) is None
