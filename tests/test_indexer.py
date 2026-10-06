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
    assert count == 4  # + nested_pkg.ads

    g = Graph(tmp_db)
    file_nodes = g.nodes(kind="file", language="ada")
    assert len(file_nodes) == 4


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


def test_ada_calls_edge(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(tmp_db)
    # Geometry.Distance calls Ada.Numerics.Elementary_Functions.Sqrt (a function_call)
    distance = g.node_by_qualified_name("Geometry.Distance")
    assert distance is not None
    calls = g.edges_from(distance["id"], kinds=["calls"])
    callee_ids = {e["target_id"] for e in calls}
    from codegraph.models import stable_id

    assert stable_id("function:ada:Ada.Numerics.Elementary_Functions.Sqrt") in callee_ids


def test_ada_type_references_in_uses(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(db_path=tmp_db)

    # Distance(A, B : Point) return Float — should reference Geometry.Point (real node)
    distance = g.node_by_qualified_name("Geometry.Distance")
    assert distance is not None
    used = g.nodes_used_by(distance["id"])
    used_qnames = {n["qualified_name"] for n in used}
    assert "Geometry.Point" in used_qnames

    # The Geometry.Point reference should be the REAL node (not a placeholder)
    point_in_used = next(n for n in used if n["qualified_name"] == "Geometry.Point")
    assert point_in_used["file_path"] is not None

    # Circle has Center : Point and Radius : Float
    circle = g.node_by_qualified_name("Geometry.Circle")
    assert circle is not None
    used = g.nodes_used_by(circle["id"])
    used_qnames = {n["qualified_name"] for n in used}
    assert "Geometry.Point" in used_qnames


def test_ada_unqualified_call_resolves_to_package_scope(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    g = Graph(tmp_db)
    # Translate calls Distance without qualification — should resolve to Geometry.Distance
    translate = g.node_by_qualified_name("Geometry.Translate")
    assert translate is not None
    calls = g.edges_from(translate["id"], kinds=["calls"])
    callee_ids = {e["target_id"] for e in calls}
    from codegraph.models import stable_id

    assert stable_id("function:ada:Geometry.Distance") in callee_ids


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


def _package_contains_pairs(g):
    pkgs = {p["id"]: p["qualified_name"] for p in g.nodes(kind="package", language="ada")}
    pairs = set()
    for pid, qname in pkgs.items():
        for e in g.edges_from(pid, kinds=["contains"]):
            if e["target_id"] in pkgs:
                pairs.add((qname, pkgs[e["target_id"]]))
    return pairs


def test_ada_package_nesting_contains_edges(tmp_db):
    idx = Indexer(tmp_db)
    idx.index(FIXTURES / "ada")
    idx.close()

    pairs = _package_contains_pairs(Graph(tmp_db))
    # Dotted child unit: parent package contains child package
    assert ("Geometry", "Geometry.Utils") in pairs
    # Physically nested package is qualified by its enclosing package
    assert ("Outer", "Outer.Inner") in pairs


def test_ada_reindex_gives_identical_node_and_edge_ids(tmp_path):
    def snapshot(db):
        idx = Indexer(db)
        idx.index(FIXTURES / "ada")
        idx.close()
        g = Graph(db)
        nodes = {n["id"] for n in g.nodes(language="ada")}
        edges = {e["id"] for n in nodes for e in g.edges_from(n)}
        return nodes, edges

    first = snapshot(tmp_path / "a.duckdb")
    second = snapshot(tmp_path / "b.duckdb")
    assert first == second
    assert first[1]


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
