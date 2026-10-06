"""Scale policy primitives: per-node fan-out cap, Stub nodes and paging. Graphs built via the mutation API."""
from __future__ import annotations
import pytest

from codegraph.indexer import Indexer
from codegraph.query import Graph


@pytest.fixture
def hub(tmp_path):
    """hub is called by c00..c09 (10 callers) and calls t00..t02; c00 is also called by deep0..deep3."""
    db = tmp_path / "hub.duckdb"
    idx = Indexer(db)
    add = lambda n: idx.add_node("function", n, "cpp", qualified_name=n, file_path=f"/r/{n}.cpp")
    ids = {"hub": add("hub")}
    for i in range(10):
        ids[f"c{i:02d}"] = add(f"c{i:02d}")
        idx.add_edge("calls", ids[f"c{i:02d}"], ids["hub"])
    for i in range(3):
        ids[f"t{i:02d}"] = add(f"t{i:02d}")
        idx.add_edge("calls", ids["hub"], ids[f"t{i:02d}"])
    for i in range(4):
        ids[f"deep{i}"] = add(f"deep{i}")
        idx.add_edge("calls", ids[f"deep{i}"], ids["c00"])
    idx.add_edge("inherits", ids["t00"], ids["hub"])
    idx.close()
    g = Graph(db)
    g.ids = ids
    yield g
    g.close()


def names(r):
    return {n["name"] for n in r["nodes"]}


def test_per_node_cap_keeps_first_neighbours_by_name_and_emits_a_stub_for_the_rest(hub):
    r = hub.neighborhood(hub.ids["hub"], direction="in", depth=1, edge_kinds=["calls"], per_node_cap=4)
    assert names(r) == {"hub", "c00", "c01", "c02", "c03"}
    assert r["stubs"] == [{
        "id": f"stub:{hub.ids['hub']}:in:calls", "owner": hub.ids["hub"],
        "direction": "in", "kind": "calls", "hidden": 6, "offset": 4,
    }]
    assert r["truncated"] is False  # fan-out is not budget truncation


def test_cap_applies_per_edge_kind_and_direction(hub):
    r = hub.neighborhood(hub.ids["hub"], direction="both", depth=1, per_node_cap=2)
    got = {(s["direction"], s["kind"]): s["hidden"] for s in r["stubs"]}
    assert got == {("in", "calls"): 8, ("out", "calls"): 1}  # inherits(in)=1 fits the cap


def test_no_stub_when_a_group_fits_the_cap(hub):
    r = hub.neighborhood(hub.ids["hub"], direction="out", depth=1, edge_kinds=["calls"], per_node_cap=3)
    assert r["stubs"] == []


def test_cap_applies_to_nodes_in_outer_rings_but_not_beyond_the_depth(hub):
    r = hub.neighborhood(hub.ids["hub"], direction="in", depth=2, edge_kinds=["calls"], per_node_cap=4)
    # c00 (ring 1) was expanded in ring 2: its 4 callers fit the cap; only the hub overflowed.
    assert {s["owner"]: s["hidden"] for s in r["stubs"]} == {hub.ids["hub"]: 6}
    r = hub.neighborhood(hub.ids["hub"], direction="in", depth=2, edge_kinds=["calls"], per_node_cap=3)
    assert {s["owner"]: s["hidden"] for s in r["stubs"]} == {hub.ids["hub"]: 7, hub.ids["c00"]: 1}


def test_stubs_of_nodes_cut_by_the_limit_are_dropped(hub):
    r = hub.neighborhood(hub.ids["hub"], direction="in", depth=2, edge_kinds=["calls"],
                         per_node_cap=3, limit=1)
    assert r["truncated"] is True
    assert {s["owner"] for s in r["stubs"]} == {hub.ids["hub"]}


def test_no_cap_means_no_stubs(hub):
    assert hub.neighborhood(hub.ids["hub"], depth=1)["stubs"] == []


def test_neighbors_page_continues_where_the_capped_view_stopped(hub):
    first = hub.neighborhood(hub.ids["hub"], direction="in", depth=1, edge_kinds=["calls"], per_node_cap=4)
    stub = first["stubs"][0]
    p = hub.neighbors_page(hub.ids["hub"], "in", "calls", offset=stub["offset"], limit=4)
    assert [n["name"] for n in p["nodes"]] == ["c04", "c05", "c06", "c07"]
    assert (p["total"], p["hidden"]) == (10, 2)
    assert {(e["source_id"], e["target_id"]) for e in p["edges"]} == {(n["id"], hub.ids["hub"]) for n in p["nodes"]}
    assert {n["depth"] for n in p["nodes"]} == {1}
    last = hub.neighbors_page(hub.ids["hub"], "in", "calls", offset=8, limit=4)
    assert [n["name"] for n in last["nodes"]] == ["c08", "c09"] and last["hidden"] == 0


def test_neighbors_page_outbound_and_unknown_node(hub):
    p = hub.neighbors_page(hub.ids["hub"], "out", "calls", offset=1, limit=5)
    assert [n["name"] for n in p["nodes"]] == ["t01", "t02"]
    assert hub.neighbors_page("nope", "out", "calls") is None


def test_reach_modes_apply_the_cap_too(hub):
    r = hub.reach(hub.ids["hub"], mode="impact", depth=1, per_node_cap=4)
    assert names(r) == {"hub", "c00", "c01", "c02", "c03", "t00"}  # t00 inherits hub: its own group
    assert [(s["direction"], s["kind"], s["hidden"]) for s in r["stubs"]] == [("in", "calls", 6)]
    both = hub.reach(hub.ids["hub"], mode="both", depth=1, per_node_cap=2)
    assert {(s["direction"], s["hidden"]) for s in both["stubs"]} == {("in", 8), ("out", 1)}
    assert hub.reach(hub.ids["hub"], mode="both", depth=1)["stubs"] == []
