"""Integration tests at the HTTP API seam: /api/neighborhood and /api/node."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.models import stable_id
from codegraph.vis.app import create_app

SHAPE = stable_id("class:cpp:Shape")
CIRCLE = stable_id("class:cpp:Circle")
GEOMETRY = stable_id("package:ada:Geometry")


@pytest.fixture
def client(indexed_db):
    with TestClient(create_app(indexed_db)) as c:
        yield c


def qnames(body):
    return {n["qualified_name"] for n in body["nodes"]}


def test_neighborhood_returns_shared_graph_shape(client):
    r = client.get(f"/api/neighborhood/{SHAPE}")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"focus", "nodes", "edges", "truncated", "total", "ring_counts"}
    assert body["focus"] == SHAPE
    assert body["truncated"] is False
    assert body["total"] == len(body["nodes"])
    focus = next(n for n in body["nodes"] if n["id"] == SHAPE)
    assert focus["depth"] == 0 and focus["kind"] == "class" and focus["language"] == "cpp"
    assert {"id", "kind", "name", "qualified_name", "path", "line_start", "line_end",
            "language", "depth", "external"} <= set(focus)
    assert {"id", "kind", "source_id", "target_id"} <= set(body["edges"][0])


def test_inbound_inherits_gives_the_type_hierarchy_children(client):
    body = client.get(f"/api/neighborhood/{SHAPE}", params={"direction": "in", "kinds": "inherits"}).json()
    assert qnames(body) == {"Shape", "Circle", "Rectangle"}
    assert {n["depth"] for n in body["nodes"] if n["qualified_name"] != "Shape"} == {1}
    assert {e["kind"] for e in body["edges"]} == {"inherits"}


def test_outbound_direction_from_a_child_reaches_its_parent(client):
    body = client.get(f"/api/neighborhood/{CIRCLE}", params={"direction": "out", "kinds": "inherits"}).json()
    assert qnames(body) == {"Circle", "Shape"}


def test_depth_extends_the_neighborhood(client):
    d1 = client.get(f"/api/neighborhood/{CIRCLE}", params={"depth": 1, "kinds": "inherits"}).json()
    d2 = client.get(f"/api/neighborhood/{CIRCLE}", params={"depth": 2, "kinds": "inherits"}).json()
    assert "Rectangle" not in qnames(d1)
    assert "Rectangle" in qnames(d2)


def test_kinds_accepts_a_comma_separated_list(client):
    body = client.get(f"/api/neighborhood/{SHAPE}", params={"kinds": "inherits,contains"}).json()
    assert {e["kind"] for e in body["edges"]} == {"inherits", "contains"}


def test_limit_truncates_and_reports_total(client):
    body = client.get(f"/api/neighborhood/{SHAPE}", params={"limit": 2}).json()
    assert len(body["nodes"]) == 2
    assert body["truncated"] is True
    assert body["total"] > 2


def test_limit_above_server_maximum_is_rejected(client):
    assert client.get(f"/api/neighborhood/{SHAPE}", params={"limit": 501}).status_code == 422


def test_depth_above_server_maximum_is_rejected(client):
    assert client.get(f"/api/neighborhood/{SHAPE}", params={"depth": 11}).status_code == 422


def test_bad_direction_is_rejected(client):
    assert client.get(f"/api/neighborhood/{SHAPE}", params={"direction": "sideways"}).status_code == 422


def test_unknown_node_is_404(client):
    assert client.get("/api/neighborhood/no-such-node").status_code == 404
    assert client.get("/api/node/no-such-node").status_code == 404


def test_qualified_name_resolves_when_not_an_id(client):
    body = client.get("/api/neighborhood/Geometry.Utils").json()
    assert body["focus"] == stable_id("package:ada:Geometry.Utils")


def test_paths_are_relative_to_common_ancestor_of_indexed_files(client):
    body = client.get(f"/api/neighborhood/{SHAPE}", params={"depth": 2}).json()
    paths = {n["path"] for n in body["nodes"] if n["path"]}
    assert "cpp/shapes.cpp" in paths
    assert not any(p.startswith("/") for p in paths)
    file_node = next(n for n in body["nodes"] if n["kind"] == "file")
    assert file_node["qualified_name"] == "cpp/shapes.cpp"


def test_external_placeholders_are_flagged(client):
    body = client.get(f"/api/neighborhood/{stable_id('function:ada:Geometry.Distance')}",
                      params={"depth": 2}).json()
    ext = {n["qualified_name"] for n in body["nodes"] if n["external"]}
    assert "Ada.Numerics.Elementary_Functions.Sqrt" in ext
    assert not any(n["external"] for n in body["nodes"] if n["kind"] == "file")


def test_node_detail_has_path_defining_files_and_neighbour_counts(client):
    body = client.get(f"/api/node/{SHAPE}").json()
    assert body["qualified_name"] == "Shape" and body["kind"] == "class"
    assert body["path"] == "cpp/shapes.cpp"
    assert body["defining_files"] == ["cpp/shapes.cpp"]
    assert body["neighbour_counts"] == {"in": {"contains": 1, "inherits": 2}, "out": {"contains": 2}}


def test_node_detail_lists_every_defining_file(client):
    body = client.get(f"/api/node/{GEOMETRY}").json()
    assert body["defining_files"] == ["ada/geometry.adb", "ada/geometry.ads"]


def test_every_script_and_module_the_page_references_is_served(client):
    import re
    html = client.get("/").text
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
    assert "vendor/cytoscape.min.js" in srcs and "vendor/d3-force.min.js" in srcs and "main.js" in srcs
    seen, todo = set(), list(srcs)
    while todo:
        src = todo.pop()
        if src in seen:
            continue
        seen.add(src)
        r = client.get("/" + src)
        assert r.status_code == 200, src
        if src.endswith(".js") and not src.startswith("vendor/"):  # follow relative ES imports
            todo += [m[2:] for m in re.findall(r'from "(\./[^"]+)"', r.text)]
    assert {"api.js", "state.js", "canvas.js", "layout.js", "elements.js", "panel.js", "style.js"} <= seen


def test_neighbour_counts_match_the_neighborhood_edges(client):
    node = client.get(f"/api/node/{SHAPE}").json()
    hood = client.get(f"/api/neighborhood/{SHAPE}").json()
    inherits_in = {e["source_id"] for e in hood["edges"] if e["kind"] == "inherits" and e["target_id"] == SHAPE}
    assert len(inherits_in) == node["neighbour_counts"]["in"]["inherits"]
