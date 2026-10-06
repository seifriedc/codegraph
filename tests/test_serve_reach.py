"""Integration tests: Impact set / Dependencies modes of /api/neighborhood, on the fixtures."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.models import stable_id
from codegraph.vis.app import create_app

SHAPE = stable_id("class:cpp:Shape")
CIRCLE = stable_id("class:cpp:Circle")
TOTAL_AREA = stable_id("function:cpp:total_area")


@pytest.fixture
def client(indexed_db):
    with TestClient(create_app(indexed_db)) as c:
        yield c


def get(client, node, **params):
    r = client.get(f"/api/neighborhood/{node}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def qnames(body, kind=None):
    return {n["qualified_name"] for n in body["nodes"] if kind is None or n["kind"] == kind}


def test_impact_of_a_base_class_is_its_descendants(client):
    body = get(client, SHAPE, mode="impact", depth=1)
    assert {"Shape", "Circle", "Rectangle"} <= qnames(body)
    assert {e["kind"] for e in body["edges"]} <= {"calls", "references", "instantiates", "inherits"}
    # Impact never walks to ancestors or to what the focus merely contains.
    assert qnames(body, "type") == set() and not any(n["kind"] == "method" for n in body["nodes"])


def test_impact_of_a_derived_class_does_not_include_its_base(client):
    body = get(client, CIRCLE, mode="impact", depth=2)
    assert "Shape" not in qnames(body)


def test_dependencies_of_a_derived_class_include_its_base(client):
    body = get(client, CIRCLE, mode="dependencies", depth=1)
    assert "Shape" in qnames(body)
    assert "Rectangle" not in qnames(body)


def test_dependencies_of_a_base_class_do_not_include_descendants(client):
    body = get(client, SHAPE, mode="dependencies", depth=3)
    assert not ({"Circle", "Rectangle"} & qnames(body))


def test_both_is_impact_union_dependencies(client):
    imp = get(client, CIRCLE, mode="impact", depth=2)
    dep = get(client, CIRCLE, mode="dependencies", depth=2)
    both = get(client, CIRCLE, mode="both", depth=2)
    assert {n["id"] for n in both["nodes"]} == {n["id"] for n in imp["nodes"]} | {n["id"] for n in dep["nodes"]}


def test_ring_counts_are_reported_per_depth(client):
    body = get(client, SHAPE, mode="impact", depth=2)
    rings = body["ring_counts"]
    by_depth = {}
    for n in body["nodes"]:
        by_depth[n["depth"]] = by_depth.get(n["depth"], 0) + 1
    assert rings == {str(d): c for d, c in by_depth.items() if d >= 1}


def test_ring_counts_stay_untruncated_when_limit_applies(client):
    full = get(client, SHAPE, mode="impact", depth=2)
    cut = get(client, SHAPE, mode="impact", depth=2, limit=1)
    assert cut["truncated"] is True and len(cut["nodes"]) == 1
    assert cut["ring_counts"] == full["ring_counts"]


def test_plain_neighborhood_has_no_ring_counts(client):
    assert get(client, SHAPE)["ring_counts"] is None


def test_bad_mode_is_rejected(client):
    assert client.get(f"/api/neighborhood/{SHAPE}", params={"mode": "sideways"}).status_code == 422


def test_depth_all_is_the_server_maximum_and_above_is_rejected(client):
    assert get(client, SHAPE, mode="impact", depth=10)["focus"] == SHAPE
    assert client.get(f"/api/neighborhood/{SHAPE}", params={"mode": "impact", "depth": 11}).status_code == 422


def test_unknown_node_is_404_in_a_mode(client):
    assert client.get("/api/neighborhood/nope", params={"mode": "impact"}).status_code == 404
