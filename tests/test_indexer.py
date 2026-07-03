"""Integration tests: index fixture files and verify node/edge counts."""
from __future__ import annotations
import pytest
from pathlib import Path
from codegraph.indexer import Indexer
from codegraph.query import Graph

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.duckdb"


# ── Ada ───────────────────────────────────────────────────────────────────────

def test_ada_creates_file_nodes(tmp_db):
    idx = Indexer(tmp_db)
    count = idx.index(FIXTURES / "ada")
    idx.close()
    assert count == 3  # geometry.ads + geometry.adb + child_pkg.ads

    g = Graph(tmp_db)
    file_nodes = g.nodes(kind="file", language="ada")
    assert len(file_nodes) == 3


def test_ada_extracts_package(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(tmp_db)
    pkgs = g.nodes(kind="package", language="ada")
    assert len(pkgs) >= 1
    names = {p["name"] for p in pkgs}
    assert "Geometry" in names


def test_ada_extracts_functions(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(tmp_db)
    fns = g.nodes(kind="function", language="ada")
    names = {f["name"] for f in fns}
    assert "Distance" in names
    assert "Translate" in names


def test_ada_dotted_package_qualified_names(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(tmp_db)
    pkgs = g.nodes(kind="package", language="ada")
    pkg_map = {p["qualified_name"]: p for p in pkgs}

    # Dotted package must use full dotted qualified name, not just the last component
    assert "Geometry.Utils" in pkg_map
    assert pkg_map["Geometry.Utils"]["name"] == "Utils"

    # Children of the dotted package must also be fully qualified
    fns = g.nodes(kind="function", language="ada")
    fn_qnames = {f["qualified_name"] for f in fns}
    assert "Geometry.Utils.Blend" in fn_qnames

    types = g.nodes(kind="type", language="ada")
    type_qnames = {t["qualified_name"] for t in types}
    assert "Geometry.Utils.Color" in type_qnames


def test_ada_record_components(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(tmp_db)
    fields = g.nodes(kind="field", language="ada")
    field_qnames = {f["qualified_name"] for f in fields}

    # Point record: X, Y
    assert "Geometry.Point.X" in field_qnames
    assert "Geometry.Point.Y" in field_qnames

    # Shape record: Color
    assert "Geometry.Shape.Color" in field_qnames

    # declaration_hierarchy on Point should include its fields
    point = g.node_by_qualified_name("Geometry.Point")
    assert point is not None
    hierarchy = g.declaration_hierarchy(point["id"])
    hier_names = {n["name"] for n in hierarchy}
    assert "X" in hier_names
    assert "Y" in hier_names


def test_ada_imports_edge(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(tmp_db)
    ada_nodes = g.nodes(language="ada")
    imports = []
    for n in ada_nodes:
        imports.extend(g.edges_from(n["id"], kinds=["imports"]))
    assert len(imports) >= 1


# ── C ─────────────────────────────────────────────────────────────────────────

def test_c_creates_file_node(tmp_db):
    idx = Indexer(tmp_db)
    count = idx.index(FIXTURES / "c")
    idx.close()
    assert count == 1

    g = Graph(tmp_db)
    assert len(g.nodes(kind="file", language="c")) == 1


def test_c_extracts_functions(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "c")
    idx.close()

    g = Graph(tmp_db)
    fns = g.nodes(kind="function", language="c")
    names = {f["name"] for f in fns}
    assert "distance" in names
    assert "dot_product" in names
    assert "make_point" in names


def test_c_extracts_includes(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "c")
    idx.close()

    g = Graph(tmp_db)
    c_nodes = g.nodes(language="c")
    imports = []
    for n in c_nodes:
        imports.extend(g.edges_from(n["id"], kinds=["imports"]))
    assert len(imports) >= 2  # math.h + stdlib.h


# ── C++ ───────────────────────────────────────────────────────────────────────

def test_cpp_creates_file_node(tmp_db):
    idx = Indexer(tmp_db)
    count = idx.index(FIXTURES / "cpp")
    idx.close()
    assert count == 1

    g = Graph(tmp_db)
    assert len(g.nodes(kind="file", language="cpp")) == 1


def test_cpp_extracts_classes(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "cpp")
    idx.close()

    g = Graph(tmp_db)
    classes = g.nodes(kind="class", language="cpp")
    names = {c["name"] for c in classes}
    assert "Shape" in names
    assert "Circle" in names
    assert "Rectangle" in names


def test_cpp_inheritance_edges(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "cpp")
    idx.close()

    g = Graph(tmp_db)
    classes = g.nodes(kind="class", language="cpp")
    circle = next((c for c in classes if c["name"] == "Circle"), None)
    assert circle is not None

    inherits = g.edges_from(circle["id"], kinds=["inherits"])
    assert len(inherits) >= 1


def test_cpp_extracts_free_function(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "cpp")
    idx.close()

    g = Graph(tmp_db)
    fns = g.nodes(kind="function", language="cpp")
    names = {f["name"] for f in fns}
    assert "total_area" in names
