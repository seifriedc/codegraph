# Testing

Integration tests first. Unit tests are welcome for isolated primitives with rich logic (new `Graph` methods) but never replace an integration test. Assert external behaviour (responses, graph structure, counts, ordering), never implementation details or layout pixels.

## Seams (pytest, all under `tests/`)

- **Indexer/query**: index `tests/fixtures/{ada,c,cpp}/` into a `tmp_path` DuckDB and assert on graph structure (`test_indexer.py`, `test_query.py`).
- **API** (primary for the visualization): `TestClient(create_app(db))` over a temp DB indexed from the fixtures. `tests/conftest.py` provides the `indexed_db` fixture. Cover endpoint contracts, filters, caps/truncation, relative paths and read-only behaviour here.
- **Scale/cap**: build graphs through the mutation API (`add_node`/`add_edge`) with the cap values as parameters; the fixtures are too small to hit real caps.
- **OpenAPI snapshot**: `test_openapi_snapshot.py` compares the FastAPI schema to `tests/snapshots/openapi.json`. A failure means update the UI client (`api.js` and callers), regenerate with `pytest tests/test_openapi_snapshot.py --update-openapi-snapshot`, and commit both.
- **Packaging**: `test_packaging.py` builds the wheel and checks the static bundle (including `vendor/`) ships in it.

Count the fixtures rather than hard-coding totals; they grow.

## JS

`node --test tests/js/*.test.mjs` covers DOM-free modules only (URL state, search shaping, filters, scale model, layouts). It is not part of the default `pytest` run.

## Not automated

Browser rendering and physics/layout feel. Use `docs/viz-manual-checklist.md` (also holds the acceptance demo script and known v1 limitations). A Playwright end-to-end test is tracked in issue #15.
