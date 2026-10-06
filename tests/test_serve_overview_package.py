"""Overview in Package mode (group_by=package) and the externals toggle, at the HTTP seam."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from codegraph.vis.app import create_app

PKG = {"group_by": "package", "kinds": "imports,inherits,references,calls"}


@pytest.fixture
def client(indexed_db):
    with TestClient(create_app(indexed_db)) as c:
        yield c


def by_name(body, kind):
    return {n["name"]: n for n in body["nodes"] if n["group"] and n["kind"] == kind}


def test_package_mode_groups_are_ada_packages_and_c_cpp_files(client):
    body = client.get("/api/overview", params=PKG).json()
    assert body["group_by"] == "package"
    pkgs, files = by_name(body, "package"), by_name(body, "file")
    # top-level Ada Packages only: nested ones are children, not top-level Groups
    assert set(pkgs) == {"Geometry", "Outer"}
    assert all(p["parent"] is None and p["node_id"] == p["id"] for p in pkgs.values())
    # pure-Ada files are represented by their Package; C and C++ files are Groups
    assert set(files) == {"math_utils.c", "shapes.cpp"}
    assert not any(n["kind"] == "directory" for n in body["nodes"])


def test_nested_packages_collapse_and_expand_via_contains(client):
    first = client.get("/api/overview", params=PKG).json()
    outer, geometry = by_name(first, "package")["Outer"], by_name(first, "package")["Geometry"]
    assert outer["member_count"] >= 3  # Outer, Inner, Ping (+ its file)
    assert "Inner" not in by_name(first, "package") and "Utils" not in by_name(first, "package")

    second = client.get("/api/overview", params={**PKG, "expanded": [outer["id"], geometry["id"]]}).json()
    pk = by_name(second, "package")
    assert pk["Inner"]["parent"] == outer["id"] and pk["Utils"]["parent"] == geometry["id"]
    assert pk["Outer"]["expanded"] is True and pk["Inner"]["expanded"] is False

    third = client.get("/api/overview", params={**PKG, "expanded": [outer["id"], pk["Inner"]["id"]]}).json()
    members = {n["name"] for n in third["nodes"] if n["parent"] == pk["Inner"]["id"] and not n["group"]}
    assert "Ping" in members
    # the Package's own node is the Group, never repeated as a member
    assert "Inner" not in members


def test_aggregate_edges_roll_up_to_packages(client):
    body = client.get("/api/overview", params={"group_by": "package", "kinds": "imports",
                                               "externals": "true"}).json()
    ids = {n["id"]: n for n in body["nodes"]}
    ext = next(n for n in body["nodes"] if n["kind"] == "external")
    geo = by_name(body, "package")["Geometry"]
    assert any(e["source_id"] == geo["id"] and e["target_id"] == ext["id"] for e in body["edges"])
    assert all(e["source_id"] in ids and e["target_id"] in ids for e in body["edges"])


@pytest.mark.parametrize("group_by", ["directory", "package"])
def test_externals_hidden_by_default_and_one_external_group_when_shown(client, group_by):
    off = client.get("/api/overview", params={"group_by": group_by}).json()
    assert not any(n["kind"] == "external" for n in off["nodes"])
    on = client.get("/api/overview", params={"group_by": group_by, "externals": "true"}).json()
    externals = [n for n in on["nodes"] if n["kind"] == "external"]
    assert len(externals) == 1 and externals[0]["group"] and externals[0]["parent"] is None
    assert externals[0]["member_count"] > 0
    # drilling in lists the placeholders, in both groupings
    drilled = client.get("/api/overview", params={"group_by": group_by, "externals": "true",
                                                  "expanded": [externals[0]["id"]]}).json()
    assert "Sqrt" in {n["name"] for n in drilled["nodes"] if n["parent"] == "external"}
