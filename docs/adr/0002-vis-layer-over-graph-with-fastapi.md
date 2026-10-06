# Viz lives in `codegraph/vis`, built on `Graph` primitives, served by FastAPI

The `codegraph serve` visualization is a separate layer in `codegraph/vis/` (FastAPI app, pydantic response models, static bundle). It calls only `Graph` in `codegraph/query.py`, never SQL. General-purpose subgraph primitives (e.g. `Graph.neighborhood`, group overview with derived Aggregate edges) are added to `Graph` so the CLI and agents share them; JSON shaping, limits and HTTP stay in `vis`.

## Decisions

- **Layering**: `Graph` stays the single query API. `vis` is a consumer; it holds no SQL.
- **Server**: FastAPI + uvicorn. Pydantic models are the JSON contract (OpenAPI for free) and keep the door open to hosting later. Cost: pydantic and starlette as new dependencies.
- **Read-only, stateless**: `Graph(db, read_only=True)` skips DDL; one connection, a `.cursor()` per request. No server-side session state, so multiple browser tabs (or multiple `serve` processes on one file) work. View state lives in the client.
- **Contract**: `/api/neighborhood/{id}` (also serves impact analysis via `kinds=calls`, `direction`, `depth`), `/api/hierarchy/{id}?mode=type|declaration`, `/api/overview?group_by=directory|package&expanded=&kinds=&externals=`, `/api/node/{id}`, `/api/stats`, minimal `/api/search`. Graph responses share `{nodes, edges, truncated, total}`.
- **Caps**: `limit` with server default and hard max; truncation drops the deepest BFS ring first; `truncated` and `total` reported. Policy numbers and UX belong to the scale decision.
- **Paths**: returned relative to the common ancestor of indexed files, computed at serve time (no schema change).

## Considered Options

- **stdlib `ThreadingHTTPServer`**: zero deps, but hand-written routing and no schema. Rejected for readability and hosting headroom.
- **Starlette only**: smaller, but no response models; contract would be informal.
- **Everything inside `Graph`** or a `GraphView` wrapper: rejected; one query API with a thin consumer is simpler.
- **Per-request connections / one locked connection**: rejected in favour of cursor-per-request.
