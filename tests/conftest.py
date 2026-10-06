from __future__ import annotations
from pathlib import Path

import pytest

from codegraph.indexer import Indexer

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def indexed_db(tmp_path):
    """Temp DuckDB indexed from all fixture languages (ada, c, cpp)."""
    db = tmp_path / "fixtures.duckdb"
    idx = Indexer(db)
    idx.index(FIXTURES)
    idx.close()
    return db
