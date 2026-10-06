"""Graph.search ranking primitive: degree breaks ties after match tier and kind priority."""

from __future__ import annotations
import pytest

from codegraph.indexer import Indexer
from codegraph.query import Graph


@pytest.fixture
def degree_graph(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    # Same name tier and kind (functions): `popular_b` is called twice, `popular_a` never.
    (src / "m.c").write_text(
        "int popular_a(void) { return 0; }\n"
        "int popular_b(void) { return 1; }\n"
        "void u1(void) { popular_b(); }\n"
        "void u2(void) { popular_b(); }\n"
    )
    db = tmp_path / "d.duckdb"
    idx = Indexer(db)
    idx.index(src)
    idx.close()
    return Graph(db)


def test_higher_degree_ranks_first_within_same_tier_and_kind(degree_graph):
    r = degree_graph.search("popular", limit=20)
    names = [n["name"] for n in r["nodes"]]
    assert names == ["popular_b", "popular_a"]
    assert r["nodes"][0]["degree"] > r["nodes"][1]["degree"]
