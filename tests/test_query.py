"""Integration tests: traversal and high-level query API."""
from __future__ import annotations
import pytest
from pathlib import Path
from codegraph.indexer import Indexer
from codegraph.query import Graph

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cpp_graph(tmp_path):
    db = tmp_path / "cpp.duckdb"
    idx = Indexer(db)
    idx.index(FIXTURES / "cpp")
    idx.close()
    return Graph(db)


@pytest.fixture
def c_graph(tmp_path):
    db = tmp_path / "c.duckdb"
    idx = Indexer(db)
    idx.index(FIXTURES / "c")
    idx.close()
    return Graph(db)


def test_declaration_hierarchy(cpp_graph):
    shape = cpp_graph.node_by_qualified_name("Shape")
    assert shape is not None
    hierarchy = cpp_graph.declaration_hierarchy(shape["id"])
    # Shape should contain its method(s)
    assert len(hierarchy) >= 1


def test_type_hierarchy_descendants(cpp_graph):
    shape = cpp_graph.node_by_qualified_name("Shape")
    assert shape is not None
    result = cpp_graph.type_hierarchy(shape["id"])
    descendant_names = {n["name"] for n in result["descendants"]}
    assert "Circle" in descendant_names
    assert "Rectangle" in descendant_names


def test_type_hierarchy_no_ancestors_for_root(cpp_graph):
    shape = cpp_graph.node_by_qualified_name("Shape")
    assert shape is not None
    result = cpp_graph.type_hierarchy(shape["id"])
    # Shape has no parent class in the fixture
    assert result["ancestors"] == []


def test_traverse_contains_from_file(cpp_graph):
    files = cpp_graph.nodes(kind="file")
    assert files
    file_id = files[0]["id"]
    children = cpp_graph.traverse(file_id, edge_kinds=["contains"], direction="out", max_depth=1)
    names = {n["name"] for n in children}
    # File should directly contain the top-level classes and struct
    assert "Shape" in names or "Point" in names


def test_mutation_add_node(tmp_path):
    db = tmp_path / "mut.duckdb"
    idx = Indexer(db)
    idx.index(FIXTURES / "cpp")
    nid = idx.add_node(
        kind="function", name="helper", language="cpp",
        qualified_name="helper", file_path="/synthetic/helper.cpp"
    )
    idx.close()

    g = Graph(db)
    node = g.node_by_id(nid)
    assert node is not None
    assert node["name"] == "helper"


def test_mutation_add_edge(tmp_path):
    db = tmp_path / "mut.duckdb"
    idx = Indexer(db)
    idx.index(FIXTURES / "cpp")

    classes = Graph(db).nodes(kind="class", language="cpp")
    circle = next(c for c in classes if c["name"] == "Circle")
    rect = next(c for c in classes if c["name"] == "Rectangle")

    eid = idx.add_edge(kind="references", source_id=circle["id"], target_id=rect["id"])
    idx.close()

    g = Graph(db)
    edges = g.edges_from(circle["id"], kinds=["references"])
    assert any(e["id"] == eid for e in edges)


def test_update_node_metadata(tmp_path):
    db = tmp_path / "mut.duckdb"
    idx = Indexer(db)
    idx.index(FIXTURES / "c")
    idx.close()

    g = Graph(db)
    fns = g.nodes(kind="function", language="c")
    fn = next(f for f in fns if f["name"] == "distance")

    idx2 = Indexer(db)
    idx2.update_node_metadata(fn["id"], {"complexity": 5, "reviewed": True})
    idx2.close()

    g2 = Graph(db)
    updated = g2.node_by_id(fn["id"])
    import json
    meta = json.loads(updated["metadata"]) if isinstance(updated["metadata"], str) else updated["metadata"]
    assert meta.get("complexity") == 5
