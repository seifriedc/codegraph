"""Integration tests at the HTTP API seam: TestClient over a fixture-indexed temp DB."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.vis.app import create_app


@pytest.fixture
def client(indexed_db):
    with TestClient(create_app(indexed_db)) as c:
        yield c


def test_stats_reports_counts_for_indexed_fixtures(client):
    body = client.get("/api/stats").json()
    assert body["total_files"] == 5  # 3 ada + 1 c + 1 cpp
    assert body["total_nodes"] > 0 and body["total_edges"] > 0
    assert set(body["nodes_by_language"]) >= {"ada", "c", "cpp"}
    assert body["nodes_by_kind"]["file"] == 5
    assert body["edges_by_kind"]


def test_root_serves_placeholder_bundle(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "codegraph" in r.text.lower()


def test_bundle_modules_are_served(client):
    r = client.get("/main.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_serving_never_modifies_the_database(indexed_db):
    before = indexed_db.read_bytes()
    with TestClient(create_app(indexed_db)) as c:
        c.get("/api/stats")
        c.get("/")
    assert indexed_db.read_bytes() == before


def test_two_servers_share_one_database(indexed_db):
    with TestClient(create_app(indexed_db)) as a, TestClient(create_app(indexed_db)) as b:
        assert a.get("/api/stats").json() == b.get("/api/stats").json()


def test_missing_database_fails_at_startup(tmp_path):
    with pytest.raises(Exception):
        create_app(tmp_path / "nope.duckdb")


def test_api_routes_are_not_shadowed_by_static_mount(client):
    assert client.get("/api/does-not-exist").status_code == 404
