"""Integration tests at the HTTP API seam: /api/hierarchy (mode=type|declaration)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.models import stable_id
from codegraph.vis.app import create_app

SHAPE = stable_id("class:cpp:Shape")
CIRCLE = stable_id("class:cpp:Circle")
RECTANGLE = stable_id("class:cpp:Rectangle")


@pytest.fixture
def client(indexed_db):
    with TestClient(create_app(indexed_db)) as c:
        yield c


def qnames(body):
    return {n["qualified_name"] for n in body["nodes"]}


def test_type_hierarchy_of_the_root_returns_its_descendants_with_inherits_edges(client):
    r = client.get(f"/api/hierarchy/{SHAPE}", params={"mode": "type"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"focus", "nodes", "edges", "stubs", "truncated", "total", "ring_counts"}
    assert body["ring_counts"] is None  # rings are a reach-view concept
    assert body["focus"] == SHAPE
    assert qnames(body) == {"Shape", "Circle", "Rectangle"}
    # edges point child -> parent, so dagre puts the parent on top
    assert {(e["source_id"], e["target_id"], e["kind"]) for e in body["edges"]} == {
        (CIRCLE, SHAPE, "inherits"), (RECTANGLE, SHAPE, "inherits")}
    assert body["truncated"] is False and body["total"] == 3


def test_type_hierarchy_of_a_leaf_includes_its_ancestors_but_not_siblings(client):
    body = client.get(f"/api/hierarchy/{CIRCLE}", params={"mode": "type"}).json()
    assert qnames(body) == {"Circle", "Shape"}


def test_hierarchy_accepts_a_qualified_name(client):
    assert client.get("/api/hierarchy/Shape", params={"mode": "type"}).json()["focus"] == SHAPE


def test_unknown_node_is_404(client):
    assert client.get("/api/hierarchy/nope", params={"mode": "type"}).status_code == 404


def test_mode_is_required_and_validated(client):
    assert client.get(f"/api/hierarchy/{SHAPE}").status_code == 422
    assert client.get(f"/api/hierarchy/{SHAPE}", params={"mode": "bogus"}).status_code == 422


def test_declaration_hierarchy_returns_the_contained_members(client):
    body = client.get(f"/api/hierarchy/{CIRCLE}", params={"mode": "declaration"}).json()
    names = qnames(body)
    assert {"Circle", "Circle::area", "Circle::name"} <= names
    assert "Shape" not in names and "Rectangle::area" not in names
    assert {e["kind"] for e in body["edges"]} <= {"contains", "defines"}
    ids = {n["id"] for n in body["nodes"]}
    assert all(e["source_id"] in ids and e["target_id"] in ids for e in body["edges"])
    # parent -> member, so dagre puts the container on top
    area = next(n["id"] for n in body["nodes"] if n["qualified_name"] == "Circle::area")
    assert any(e["source_id"] == CIRCLE and e["target_id"] == area for e in body["edges"])


def test_limit_truncates_but_keeps_the_focus(client):
    body = client.get(f"/api/hierarchy/{SHAPE}", params={"mode": "type", "limit": 2}).json()
    assert len(body["nodes"]) == 2 and SHAPE in {n["id"] for n in body["nodes"]}
    assert body["truncated"] is True and body["total"] == 3
