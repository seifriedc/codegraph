"""FastAPI application factory for `codegraph serve`."""
from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Iterator

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from codegraph.query import Graph
from codegraph.vis import focus
from codegraph.vis.models import StatsResponse
from codegraph.vis.paths import common_root, make_relativizer


def static_dir() -> Path:
    """Directory of the prebuilt UI bundle shipped as package data."""
    return Path(str(resources.files("codegraph.vis") / "static"))


def create_app(db_path: str | Path) -> FastAPI:
    """Build a read-only app over an indexed database.

    One read-only connection is opened here; each request gets its own cursor.
    No server-side state is kept. Raises if the database cannot be opened.
    """
    root = Graph(db_path, read_only=True)
    app = FastAPI(title="codegraph", on_shutdown=[root.close])

    def get_graph() -> Iterator[Graph]:
        g = root.cursor()
        try:
            yield g
        finally:
            g.close()

    @app.get("/api/stats", response_model=StatsResponse)
    def stats(g: Graph = Depends(get_graph)) -> dict:
        return g.demographics()

    rel = make_relativizer(common_root([f["file_path"] for f in root.nodes(kind="file")]))
    focus.register(app, get_graph, rel)

    # Mounted last so /api routes win; serves index.html at "/".
    app.mount("/", StaticFiles(directory=static_dir(), html=True), name="static")
    return app
