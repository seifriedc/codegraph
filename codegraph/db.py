from __future__ import annotations
from pathlib import Path

import duckdb

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS nodes (
        id             VARCHAR PRIMARY KEY,
        kind           VARCHAR NOT NULL,
        name           VARCHAR NOT NULL,
        qualified_name VARCHAR,
        file_path      VARCHAR,
        line_start     INTEGER,
        line_end       INTEGER,
        language       VARCHAR,
        metadata       JSON
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS edges (
        id          VARCHAR PRIMARY KEY,
        kind        VARCHAR NOT NULL,
        source_id   VARCHAR,
        target_id   VARCHAR,
        file_path   VARCHAR,
        line        INTEGER,
        col         INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_qname  ON nodes(qualified_name)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_file   ON nodes(file_path)",
]

_INSERT_NODE = """
    INSERT INTO nodes (id, kind, name, qualified_name, file_path, line_start, line_end, language, metadata)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (id) DO UPDATE SET
        file_path  = COALESCE(excluded.file_path,  nodes.file_path),
        line_start = COALESCE(excluded.line_start, nodes.line_start),
        line_end   = COALESCE(excluded.line_end,   nodes.line_end)
"""

_INSERT_EDGE = """
    INSERT INTO edges (id, kind, source_id, target_id, file_path, line, col)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (id) DO NOTHING
"""


def connect(db_path: str | Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the database. Read-only opens skip DDL and can be shared across processes."""
    if read_only:
        return duckdb.connect(str(db_path), read_only=True)
    conn = duckdb.connect(str(db_path))
    for ddl in _DDL:
        conn.execute(ddl)
    return conn


def insert_nodes(conn: duckdb.DuckDBPyConnection, nodes: list) -> None:
    import json
    if not nodes:
        return
    conn.executemany(
        _INSERT_NODE,
        [
            (n.id, n.kind, n.name, n.qualified_name,
             n.file_path, n.line_start, n.line_end,
             n.language, json.dumps(n.metadata))
            for n in nodes
        ],
    )


def insert_edges(conn: duckdb.DuckDBPyConnection, edges: list) -> None:
    if not edges:
        return
    conn.executemany(
        _INSERT_EDGE,
        [
            (e.id, e.kind, e.source_id, e.target_id,
             e.file_path, e.line, e.col)
            for e in edges
        ],
    )
