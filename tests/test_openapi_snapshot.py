"""The FastAPI-generated OpenAPI schema must equal the committed snapshot.

The JS client (codegraph/vis/static/api.js and its callers) is written by hand against this
contract, so any API change must be a deliberate, reviewed one.
Regenerate with:  pytest tests/test_openapi_snapshot.py --update-openapi-snapshot
"""

from __future__ import annotations
import json
from pathlib import Path

from codegraph.vis.app import create_app

SNAPSHOT = Path(__file__).parent / "snapshots" / "openapi.json"


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def test_openapi_schema_matches_committed_snapshot(indexed_db, request):
    actual = render(create_app(indexed_db).openapi())
    if request.config.getoption("--update-openapi-snapshot"):
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(actual)
        return
    assert SNAPSHOT.exists(), (
        "No OpenAPI snapshot. Run: pytest tests/test_openapi_snapshot.py --update-openapi-snapshot"
    )
    assert actual == SNAPSHOT.read_text(), (
        "The HTTP API contract changed (OpenAPI schema differs from tests/snapshots/openapi.json).\n"
        "1. Update the JS client: codegraph/vis/static/api.js and every caller affected by the change.\n"
        "2. Regenerate the snapshot: pytest tests/test_openapi_snapshot.py --update-openapi-snapshot\n"
        "3. Review and commit the snapshot diff together with the client changes."
    )
