# Research: web server and wheel packaging (issue #3)

Part of map #1. Facts and trade-offs only; no decision. Researched 2026-10-02.

## Local facts (repo at `main` f313960)

- **Build backend is setuptools only.** `pyproject.toml`: `requires = ["setuptools>=68"]`, `[tool.setuptools.packages.find] include = ["codegraph*"]`. No `package-data`, no `MANIFEST.in`.
- **The maturin/Rust crate no longer exists.** Commit `fa68395` ("Remove Rust extension, port all logic back to Python") deleted `codegraph_core/` and "Switched build backend from maturin to setuptools"; `e626cd1` removed root `Cargo.toml`. CLAUDE.md still describes `codegraph_core` as a placeholder; it is stale. Maturin sections below apply only if Rust is reintroduced.
- **Runtime deps today:** duckdb>=1.1, typer>=0.12, tree-sitter + 4 grammars (pyproject.toml). uv.lock pins duckdb 1.5.4.
- **DB access:** `codegraph/db.py::connect()` calls `duckdb.connect(str(path))` (read-write, default mode) and then runs `CREATE TABLE/INDEX IF NOT EXISTS` DDL on every open. `Graph.__init__` stores one `self.conn`; `_fetchall` runs `self.conn.execute(...)`. Each CLI command builds `Graph(db)` once. So `Graph` today opens writable and issues DDL (a write on open); a `read_only=True` open would need the DDL skipped.
- `Dockerfile` installs via `pip install uv` + `.[dev]` (dev only; not a distribution path).

## Q1. Server options

### A. stdlib `http.server`
- `ThreadingHTTPServer` "is identical to HTTPServer but uses threads to handle requests" (one thread per request). [py-http]
- `http.server` "is not recommended for production. It only implements basic security checks." [py-http] Local-only, read-only use is the intended context here.
- `SimpleHTTPRequestHandler(..., directory=None)` serves files from a directory, mapping paths directly; content type via `extensions_map`, falling back to `mimetypes` then `application/octet-stream`. [py-http] JSON routes need a custom handler subclass (routing, query-string parsing, JSON encoding hand-written).
- Default protocol is HTTP/1.0; HTTP/1.1 keep-alive requires accurate `Content-Length` on every response. [py-http]
- Dependency weight: none (stdlib). Install impact: zero.

### B. Starlette + uvicorn
- Starlette 1.7.0: pure-Python wheel 79 KB; required dep only `anyio` (+ `typing-extensions` on Python <3.13). [pypi-starlette]
- uvicorn 0.54.0: pure-Python wheel 87 KB; required deps `click`, `h11` (+ `typing-extensions` on <3.11). The `standard` extra adds httptools, python-dotenv, pyyaml, uvloop, watchfiles, websockets (several compiled). [pypi-uvicorn]
- `StaticFiles(directory=None, packages=None, html=False, check_dir=True, follow_symlink=False)`; `html=True` auto-serves `index.html` for directories; `packages` can point at a package's static dir. [starlette-static]
- Sync (`def`) endpoints run in a threadpool; default limit 40 concurrent threads. [starlette-threadpool]
- typer 0.27.2 metadata lists shellingham, rich, annotated-doc (no click), so uvicorn's `click` would be a new transitive dep. [pypi-typer]

### C. FastAPI + uvicorn
- FastAPI 0.142.2: wheel 144 KB; requires starlette>=0.46, pydantic>=2.9, typing-extensions, typing-inspection, annotated-doc, opentelemetry-api. [pypi-fastapi] Pydantic v2 brings a compiled core (`pydantic-core`); size not measured here.
- Adds request/response validation and OpenAPI generation over Starlette; rest of stack same as B.

### Reference: existing weight
- duckdb 1.5.6 wheels are 13-32 MB per platform [pypi-duckdb], so options above are small relative to the existing install; stdlib adds nothing.

## Q2. DuckDB connection and threading constraints

- "Each thread must use the `.cursor()` method to create a thread-local connection to the same DuckDB file based on the original connection." Scope: a single Python process. [duckdb-threads] A shared `DuckDBPyConnection` is not meant for concurrent use across threads.
- Applies to all options: `ThreadingHTTPServer` (thread per request), Starlette sync endpoints (threadpool), and async endpoints (single event-loop thread, but a blocking query stalls the loop). Current `Graph` holds one shared `self.conn`; a server would need per-request/per-thread cursors or a lock (design not decided here).
- Cross-process: "multiple processes can read from the database, but no processes can write (access_mode = 'READ_ONLY')". [duckdb-concurrency] Implication: a writable indexer process and a separate serve process conflict; multiple read-only serve processes can coexist. Exact error text not verified.
- Because `connect()` runs DDL on open, serving from a read-only handle requires a path that skips it (local fact above).

## Q3. Packaging a prebuilt JS bundle

### Under setuptools (current)
- With `pyproject.toml` config, `tool.setuptools.include-package-data` defaults to `true`; `[tool.setuptools.package-data]` takes per-package glob lists, e.g. `mypkg = ["*.txt"]`. `MANIFEST.in` files are pulled into sdist and wheel when `include-package-data` is true. Data files should live "inside the package directory" so they are readable via `importlib.resources`. [setuptools-data]
- Concretely: bundle under e.g. `codegraph/web/static/` plus `package-data` globs (and `MANIFEST.in` if the sdist must carry it). Nested-directory glob behavior not verified by a build here.
- Wheel stays pure-Python (`py3-none-any`) as long as no compiled extension is added; true today.
- Committed vs built: a committed bundle lets `pip install` from git/sdist work without node. A gitignored, CI-built bundle requires JS build to run before the sdist/wheel build; setuptools does not run npm itself (custom build step or CI ordering needed).

### Under maturin (only if Rust is reintroduced)
- Mixed layout: Python package dir beside `Cargo.toml`; "additional files in the Python source dir (but not in `.gitignore`) will be automatically included in the build outputs." [maturin-layout] A gitignored built bundle is therefore excluded by default; `include = [{ path = "...", format = "wheel" }]` (globs relative to `pyproject.toml`) can force inclusion. [maturin-config]
- `<module_name>.data/` folder options (`data`, `scripts`, `headers`) exist for files unpacked into the venv. [maturin-layout]
- Wheels become platform-specific (per OS/arch) rather than one pure wheel, so the asset is duplicated per wheel. (General consequence of a compiled extension; not separately sourced.)

### Serving packaged assets
- Starlette `StaticFiles(packages=[...])` or `directory=` at the package path; stdlib `SimpleHTTPRequestHandler(directory=...)`. Resolve the directory via `importlib.resources` (recommended by setuptools docs) rather than ad-hoc `__file__` paths. [setuptools-data]

## Trade-off summary

| | stdlib http.server | Starlette+uvicorn | FastAPI+uvicorn |
|---|---|---|---|
| New required deps | 0 | anyio, click, h11 (+typing-extensions) | + pydantic (compiled core), typing-inspection, annotated-doc, opentelemetry-api |
| Routing/JSON | hand-written | built in | built in + validation + OpenAPI |
| Static files | `directory=` | `StaticFiles` | via Starlette |
| Concurrency | thread per request | event loop + 40-thread pool for sync | same as Starlette |
| DuckDB handling | cursor per thread | cursor per thread/request | same |
| Docs stance | "not recommended for production" | n/a | n/a |

## Open / unverified
- pydantic-core and uvloop wheel sizes not measured.
- No build was run; setuptools nested package-data behavior and sdist contents unverified locally.
- Starlette docs fetched from starlette.dev (project's current domain).

## Sources
- [py-http] https://docs.python.org/3/library/http.server.html
- [duckdb-threads] https://duckdb.org/docs/current/guides/python/multiple_threads
- [duckdb-concurrency] https://duckdb.org/docs/current/connect/concurrency
- [starlette-static] https://starlette.dev/staticfiles/
- [starlette-threadpool] https://starlette.dev/threadpool/
- [setuptools-data] https://setuptools.pypa.io/en/latest/userguide/datafiles.html
- [maturin-layout] https://www.maturin.rs/project_layout
- [maturin-config] https://www.maturin.rs/config.html
- [pypi-starlette] https://pypi.org/pypi/starlette/json
- [pypi-uvicorn] https://pypi.org/pypi/uvicorn/json
- [pypi-fastapi] https://pypi.org/pypi/fastapi/json
- [pypi-duckdb] https://pypi.org/pypi/duckdb/json
- [pypi-typer] https://pypi.org/pypi/typer/json
- Local: `pyproject.toml`, `codegraph/db.py`, `codegraph/query.py`, commits `fa68395`, `e626cd1`
