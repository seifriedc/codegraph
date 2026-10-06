"""Graph read-only mode: never writes, never runs DDL, allows concurrent opens."""

from __future__ import annotations
import duckdb
import pytest

from codegraph.query import Graph


def test_two_read_only_graphs_open_concurrently(indexed_db):
    a = Graph(indexed_db, read_only=True)
    b = Graph(indexed_db, read_only=True)
    assert a.demographics()["total_nodes"] == b.demographics()["total_nodes"] > 0
    a.close()
    b.close()


def test_read_only_graph_rejects_writes(indexed_db):
    g = Graph(indexed_db, read_only=True)
    with pytest.raises(duckdb.Error):
        g.conn.execute("DELETE FROM nodes")
    g.close()


def test_read_only_graph_runs_no_ddl_on_foreign_db(tmp_path):
    # A database without codegraph tables: a writable open would create them.
    db = tmp_path / "empty.duckdb"
    duckdb.connect(str(db)).close()
    g = Graph(db, read_only=True)
    tables = g.conn.execute("SELECT count(*) FROM information_schema.tables").fetchone()[0]
    assert tables == 0
    g.close()


def test_read_only_graph_leaves_file_untouched(indexed_db):
    before = indexed_db.read_bytes()
    g = Graph(indexed_db, read_only=True)
    g.nodes()
    g.close()
    assert indexed_db.read_bytes() == before


def test_cursor_returns_graph_sharing_connection(indexed_db):
    g = Graph(indexed_db, read_only=True)
    c = g.cursor()
    assert c.demographics()["total_nodes"] == g.demographics()["total_nodes"]
