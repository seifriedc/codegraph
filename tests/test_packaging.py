"""The prebuilt UI bundle must ship inside the built wheel."""
from __future__ import annotations
import os
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def test_wheel_contains_committed_bundle_and_vendored_libraries(tmp_path):
    build_meta = pytest.importorskip("setuptools.build_meta")
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        name = build_meta.build_wheel(str(tmp_path))
    finally:
        os.chdir(cwd)
    names = zipfile.ZipFile(tmp_path / name).namelist()
    assert "codegraph/vis/static/index.html" in names
    assert "codegraph/vis/static/main.js" in names
    # Every script/module index.html references (incl. vendored libraries) ships in the wheel.
    static = ROOT / "codegraph" / "vis" / "static"
    html = (static / "index.html").read_text()
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
    assert any(s.startswith("vendor/") for s in srcs)
    for src in srcs:
        assert f"codegraph/vis/static/{src}" in names, src
    # ...and so does every committed file under static/ (modules imported by main.js, vendor/*).
    for f in static.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            assert f"codegraph/vis/static/{f.relative_to(static).as_posix()}" in names, f
