"""Integration tests at the HTTP seam: /api/search (ranking, filters, cap, path match)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.indexer import Indexer
from codegraph.vis.app import create_app


@pytest.fixture
def client(indexed_db):
    with TestClient(create_app(indexed_db)) as c:
        yield c


def search(client, q, **params):
    r = client.get("/api/search", params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_response_has_shared_graph_shape_with_total_and_truncated(client):
    body = search(client, "Shape")
    assert set(body) == {"nodes", "total", "truncated"}
    assert body["truncated"] is False and body["total"] == len(body["nodes"])
    hit = body["nodes"][0]
    assert {"id", "kind", "name", "qualified_name", "path", "language", "external", "more_paths"} <= set(hit)


def test_matching_is_case_insensitive(client):
    names = {n["qualified_name"] for n in search(client, "shape")["nodes"]}
    assert {"Shape", "Geometry.Shape"} <= names


def test_exact_ranks_before_prefix_before_substring(client):
    # exact (Circle, Geometry.Circle) < prefix (Circle::area ...) < substring (Geometry.Circle.Center)
    qn = [n["qualified_name"] for n in search(client, "Circle")["nodes"]]
    exact = [i for i, q in enumerate(qn) if q in ("Circle", "Geometry.Circle")]
    prefix = [i for i, q in enumerate(qn) if q.startswith("Circle::")]
    substring = [i for i, q in enumerate(qn) if q == "Geometry.Circle.Center"]
    assert exact and prefix and substring
    assert max(exact) < min(prefix) and max(prefix) < min(substring)


def test_kind_priority_breaks_ties_within_a_match_tier(client):
    # Both exact "Shape": the cpp class outranks the type nodes.
    kinds = [n["kind"] for n in search(client, "Shape")["nodes"] if n["name"] == "Shape"]
    assert kinds.index("class") < kinds.index("type")


def test_kind_and_language_filters(client):
    assert {n["kind"] for n in search(client, "Shape", kinds="class")["nodes"]} == {"class"}
    assert {n["language"] for n in search(client, "Shape", languages="ada")["nodes"]} == {"ada"}
    body = search(client, "Shape", kinds="class,type", languages="cpp")
    assert body["nodes"]
    assert {(n["kind"], n["language"]) for n in body["nodes"]} <= {("class", "cpp"), ("type", "cpp")}


def test_path_match_only_when_query_contains_slash_or_dot(client):
    assert search(client, "fixtures")["total"] == 0  # appears only in paths
    by_path = search(client, "cpp/shapes")
    assert by_path["total"] > 0
    assert all(n["path"] == "cpp/shapes.cpp" for n in by_path["nodes"])


def test_paths_are_relative_to_the_common_root(client):
    n = next(n for n in search(client, "total_area")["nodes"] if n["name"] == "total_area")
    assert n["path"] == "cpp/shapes.cpp"


def test_blank_query_is_rejected(client):
    assert client.get("/api/search", params={"q": ""}).status_code == 422


def test_like_wildcards_in_query_are_literal(client):
    assert search(client, "%%")["total"] == 0
    assert search(client, "_h")["total"] == 0


def test_results_are_capped_at_20_with_total_and_truncated(client):
    body = search(client, "e")  # matches many nodes
    assert body["total"] > 20
    assert len(body["nodes"]) == 20 and body["truncated"] is True


def test_same_named_entities_in_two_files_merge_into_one_node(tmp_path):
    """Pins KNOWN LIMITATION https://github.com/seifriedc/codegraph/issues/14.

    Two C files each define a static `helper`; node IDs are name-based, so they collapse
    into ONE node that lists both defining files. When the ID scheme changes (#14), this
    test is expected to fail: update it then.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.c").write_text("static int helper(void) { return 1; }\n")
    (src / "b.c").write_text("static int helper(void) { return 2; }\n")
    db = tmp_path / "t.duckdb"
    idx = Indexer(db)
    idx.index(src)
    idx.close()
    with TestClient(create_app(db)) as c:
        hits = [n for n in search(c, "helper")["nodes"] if n["name"] == "helper"]
    assert len(hits) == 1
    assert hits[0]["more_paths"] == 1
