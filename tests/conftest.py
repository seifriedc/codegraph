from __future__ import annotations
from pathlib import Path

import pytest

from codegraph.indexer import Indexer

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption(
        "--update-openapi-snapshot",
        action="store_true",
        default=False,
        help="Rewrite tests/snapshots/openapi.json from the current FastAPI schema.",
    )


@pytest.fixture
def indexed_db(tmp_path):
    """Temp DuckDB indexed from all fixture languages (ada, c, cpp)."""
    db = tmp_path / "fixtures.duckdb"
    idx = Indexer(db)
    idx.index(FIXTURES)
    idx.close()
    return db
