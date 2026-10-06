"""Integration tests at the HTTP API seam: /api/overview over the fixture index."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.vis.app import create_app


@pytest.fixture
def client(indexed_db):
    with TestClient(create_app(indexed_db)) as c:
        yield c


def by_path(body):
    return {n["path"]: n for n in body["nodes"] if n["group"]}


def test_landing_overview_is_the_top_level_directory_groups(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"group_by", "kinds", "available_kinds", "nodes", "edges", "truncated", "total"}
    assert body["group_by"] == "directory"
    groups = by_path(body)
    # paths are relative to the common ancestor of indexed files; fixtures live in ada/ c/ cpp/
    assert {"ada", "c", "cpp"} <= set(groups)
    ada = groups["ada"]
    assert ada["kind"] == "directory" and ada["parent"] is None and ada["expanded"] is False
    assert ada["member_count"] > 0 and ada["node_id"] is None
    assert body["total"] == len(body["nodes"])
    # absolute paths never leak into display fields
    assert not any((n["path"] or "").startswith("/") for n in body["nodes"])


def test_calls_is_off_by_default_and_can_be_switched_on(client):
    body = client.get("/api/overview").json()
    assert "calls" not in body["kinds"] and "calls" in body["available_kinds"]
    assert "contains" not in body["available_kinds"]
    assert not any("calls" in e["kinds"] for e in body["edges"])

    with_calls = client.get("/api/overview", params={"kinds": "calls"}).json()
    assert with_calls["kinds"] == ["calls"]
    assert all(set(e["kinds"]) == {"calls"} for e in with_calls["edges"])
    assert with_calls["edges"], "fixtures contain calls"


def test_empty_kinds_means_no_edge_kinds_not_the_default(client):
    body = client.get("/api/overview", params={"kinds": ""}).json()
    assert body["kinds"] == [] and body["edges"] == []


def test_aggregate_edge_shape(client):
    body = client.get("/api/overview", params={"kinds": "calls,imports,inherits,references"}).json()
    ids = {n["id"] for n in body["nodes"]}
    pairs = set()
    for e in body["edges"]:
        assert {"id", "source_id", "target_id", "kinds", "count"} <= set(e)
        assert e["source_id"] in ids and e["target_id"] in ids
        assert e["count"] == sum(e["kinds"].values())
        pairs.add((e["source_id"], e["target_id"]))
    assert len(pairs) == len(body["edges"]), "one Aggregate edge per directed pair"


def test_expanded_ids_come_from_the_previous_response(client):
    first = client.get("/api/overview").json()
    cpp = by_path(first)["cpp"]
    second = client.get("/api/overview", params={"expanded": [cpp["id"]]}).json()
    nodes = {n["id"]: n for n in second["nodes"]}
    assert nodes[cpp["id"]]["expanded"] is True
    shapes = next(n for n in second["nodes"] if n["path"] == "cpp/shapes.cpp")
    assert shapes["parent"] == cpp["id"] and shapes["kind"] == "file" and shapes["node_id"] == shapes["id"]

    third = client.get("/api/overview", params={"expanded": [cpp["id"], shapes["id"]]}).json()
    members = [n for n in third["nodes"] if n["parent"] == shapes["id"]]
    assert {"Circle", "Shape"} <= {m["name"] for m in members}
    assert all(not m["group"] and m["node_id"] == m["id"] for m in members)


def test_externals_flag(client):
    with_ext = client.get("/api/overview").json()
    assert any(n["kind"] == "external" for n in with_ext["nodes"])
    without = client.get("/api/overview", params={"externals": "false"}).json()
    assert not any(n["kind"] == "external" for n in without["nodes"])


def test_unknown_group_by_is_a_client_error(client):
    assert client.get("/api/overview", params={"group_by": "galaxy"}).status_code == 422
