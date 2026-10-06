"""Graph.overview: Groups and derived Aggregate edges, on a small hand-built graph."""
from __future__ import annotations
import pytest

from codegraph.indexer import Indexer
from codegraph.query import Graph


@pytest.fixture
def repo(tmp_path):
    """/r/core/{a,b}.cpp, /r/ui/c.cpp, /r/top.cpp, plus an external module.

    a1 -calls-> c1 (x2 via a2), a1 -references-> c2, c1 -calls-> b1, b1 -calls-> a1,
    a1 -calls-> a2 (same file), t1 -imports-> math.h (external).
    """
    db = tmp_path / "repo.duckdb"
    idx = Indexer(db)
    ids = {}
    for path in ["core/a.cpp", "core/b.cpp", "ui/c.cpp", "top.cpp"]:
        ids[path] = idx.add_node("file", path.split("/")[-1], "cpp", qualified_name=f"/r/{path}",
                                 file_path=f"/r/{path}")
    members = {"a1": "core/a.cpp", "a2": "core/a.cpp", "b1": "core/b.cpp",
               "c1": "ui/c.cpp", "c2": "ui/c.cpp", "t1": "top.cpp"}
    for name, path in members.items():
        ids[name] = idx.add_node("function", name, "cpp", qualified_name=name, file_path=f"/r/{path}")
        idx.add_edge("contains", ids[path], ids[name])
    ids["math.h"] = idx.add_node("module", "math.h", "cpp", qualified_name="math.h")
    for kind, s, t in [("calls", "a1", "c1"), ("calls", "a2", "c1"), ("references", "a1", "c2"),
                       ("calls", "c1", "b1"), ("calls", "b1", "a1"), ("calls", "a1", "a2"),
                       ("imports", "t1", "math.h")]:
        idx.add_edge(kind, ids[s], ids[t])
    idx.close()
    g = Graph(db)
    g.ids = ids
    yield g
    g.close()


def group_ids(r):
    return {g["id"] for g in r["groups"]}


def agg(r):
    return {(e["source_id"], e["target_id"]): e["kinds"] for e in r["edges"]}


def test_collapsed_overview_shows_top_level_directory_groups(repo):
    r = repo.overview()
    by_id = {g["id"]: g for g in r["groups"]}
    assert set(by_id) == {"dir:core", "dir:ui", repo.ids["top.cpp"], "external"}
    assert by_id["dir:core"]["kind"] == "directory"
    assert by_id["dir:core"]["parent"] is None
    assert by_id["dir:core"]["member_count"] == 5  # 2 files + 3 functions
    assert by_id[repo.ids["top.cpp"]]["kind"] == "file"
    assert r["nodes"] == []


def test_one_aggregate_edge_per_directed_pair_with_per_kind_counts(repo):
    r = repo.overview()
    core, ui, top = "dir:core", "dir:ui", repo.ids["top.cpp"]
    assert agg(r) == {
        (core, ui): {"calls": 2, "references": 1},
        (ui, core): {"calls": 1},
        (top, "external"): {"imports": 1},
    }
    core_ui = next(e for e in r["edges"] if (e["source_id"], e["target_id"]) == (core, ui))
    assert core_ui["count"] == 3
    assert not any("contains" in e["kinds"] for e in r["edges"])


def test_kind_filter_reaggregates(repo):
    r = repo.overview(kinds=["references"])
    assert agg(r) == {("dir:core", "dir:ui"): {"references": 1}}
    assert agg(repo.overview(kinds=["calls", "imports"]))[("dir:core", "dir:ui")] == {"calls": 2}


def test_contains_is_never_aggregated_even_if_asked(repo):
    assert repo.overview(kinds=["contains"])["edges"] == []


def test_externals_can_be_hidden(repo):
    r = repo.overview(externals=False)
    assert "external" not in group_ids(r)
    assert all("external" not in (e["source_id"], e["target_id"]) for e in r["edges"])


def test_unknown_group_by_is_rejected(repo):
    with pytest.raises(ValueError, match="group_by"):
        repo.overview(group_by="galaxy")


def test_expanding_a_directory_replaces_it_with_its_files_as_a_compound(repo):
    core, ui = "dir:core", "dir:ui"
    a, b = repo.ids["core/a.cpp"], repo.ids["core/b.cpp"]
    r = repo.overview(expanded=[core])
    by_id = {g["id"]: g for g in r["groups"]}
    assert set(by_id) == {core, a, b, ui, repo.ids["top.cpp"], "external"}
    assert by_id[core]["expanded"] is True
    assert by_id[a]["parent"] == core and by_id[a]["expanded"] is False
    # edges now connect the visible items: core's own edges move down to file level
    assert agg(r) == {
        (a, ui): {"calls": 2, "references": 1},
        (ui, b): {"calls": 1},
        (b, a): {"calls": 1},
        (repo.ids["top.cpp"], "external"): {"imports": 1},
    }


def test_expanding_a_file_shows_its_members(repo):
    a = repo.ids["core/a.cpp"]
    r = repo.overview(expanded=["dir:core", a])
    assert {n["name"]: n["parent"] for n in r["nodes"]} == {"a1": a, "a2": a}
    a1, a2 = repo.ids["a1"], repo.ids["a2"]
    pairs = agg(r)
    assert pairs[(a1, a2)] == {"calls": 1}  # intra-file edge appears once members are visible
    assert pairs[(a1, "dir:ui")] == {"calls": 1, "references": 1}
    assert pairs[(a2, "dir:ui")] == {"calls": 1}
    assert pairs[(repo.ids["core/b.cpp"], a1)] == {"calls": 1}


def test_expanding_a_hidden_group_has_no_effect(repo):
    # a.cpp is only visible once core is expanded
    assert repo.overview(expanded=[repo.ids["core/a.cpp"]]) == repo.overview()
