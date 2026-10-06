"""`codegraph serve` command: help text, and a real server process answering HTTP."""
from __future__ import annotations
import socket
import subprocess
import sys
import time
import urllib.request

from typer.testing import CliRunner

from codegraph.cli import app


def test_serve_is_documented_in_cli_help():
    runner = CliRunner()
    top = runner.invoke(app, ["--help"])
    assert "serve" in top.output
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    for text in ("--db", "--port", "--host", "read-only"):
        assert text in result.output


def test_serve_exits_with_error_for_missing_db(tmp_path):
    result = CliRunner().invoke(app, ["serve", "--db", str(tmp_path / "nope.duckdb")])
    assert result.exit_code != 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_serve_process_answers_root_and_stats(indexed_db):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-c", "from codegraph.cli import app; app()", "serve",
         "--db", str(indexed_db), "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 20
        while True:
            try:
                stats = urllib.request.urlopen(f"{base}/api/stats", timeout=2).read()
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.2)
        assert b"total_nodes" in stats
        assert b"codegraph" in urllib.request.urlopen(f"{base}/").read()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
