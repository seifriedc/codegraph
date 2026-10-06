"""The prebuilt UI bundle must ship inside the built wheel."""
from __future__ import annotations
import os
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def test_wheel_contains_placeholder_bundle(tmp_path):
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
