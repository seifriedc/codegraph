"""HTTP seam for the scale policy: fan-out cap, stubs and /api/expand, on a graph built via the mutation API."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.indexer import Indexer
from codegraph.models import stable_id
from codegraph.vis.app import create_app

HUB = stable_id("function:cpp:hub")


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "big.duckdb"
    idx = Indexer(db)
    add = lambda n: idx.add_node("function", n, "cpp", qualified_name=n, file_path=f"/r/{n}.cpp")
    hub = add("hub")
    for i in range(40):
        idx.add_edge("calls", add(f"caller{i:02d}"), hub)
    idx.close()
    with TestClient(create_app(db)) as c:
        yield c


def test_default_fan_out_cap_is_15_with_a_stub_for_the_rest(client):
    body = client.get(f"/api/neighborhood/{HUB}", params={"direction": "in"}).json()
    assert len(body["nodes"]) == 16
    assert body["stubs"] == [{"id": f"stub:{HUB}:in:calls", "owner": HUB, "direction": "in",
                              "kind": "calls", "hidden": 25, "offset": 15}]
    assert body["truncated"] is False


def test_per_node_cap_is_a_parameter_bounded_by_the_server(client):
    body = client.get(f"/api/neighborhood/{HUB}", params={"direction": "in", "per_node_cap": 5}).json()
    assert len(body["nodes"]) == 6 and body["stubs"][0]["hidden"] == 35
    assert client.get(f"/api/neighborhood/{HUB}", params={"per_node_cap": 0}).status_code == 422
    assert client.get(f"/api/neighborhood/{HUB}", params={"per_node_cap": 101}).status_code == 422


def test_expand_pages_in_the_next_neighbors_and_a_continuation_stub(client):
    r = client.get(f"/api/expand/{HUB}", params={"direction": "in", "kind": "calls", "offset": 15, "limit": 10})
    body = r.json()
    assert [n["name"] for n in body["nodes"]] == [f"caller{i:02d}" for i in range(15, 25)]
    assert {e["target_id"] for e in body["edges"]} == {HUB}
    assert body["owner"] == HUB and body["total"] == 40
    assert body["stub"] == {"id": f"stub:{HUB}:in:calls", "owner": HUB, "direction": "in",
                            "kind": "calls", "hidden": 15, "offset": 25}


def test_expand_last_page_has_no_stub(client):
    body = client.get(f"/api/expand/{HUB}", params={"direction": "in", "kind": "calls", "offset": 30, "limit": 10}).json()
    assert len(body["nodes"]) == 10 and body["stub"] is None


def test_expand_validates_and_404s(client):
    assert client.get("/api/expand/nope", params={"direction": "in", "kind": "calls"}).status_code == 404
    assert client.get(f"/api/expand/{HUB}", params={"direction": "both", "kind": "calls"}).status_code == 422
    assert client.get(f"/api/expand/{HUB}", params={"direction": "in"}).status_code == 422
    assert client.get(f"/api/expand/{HUB}", params={"direction": "in", "kind": "calls", "limit": 101}).status_code == 422
