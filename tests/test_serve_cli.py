"""`codegraph serve` command: help text, and a real server process answering HTTP."""

from __future__ import annotations
import re
import socket
import subprocess
import sys
import time
import urllib.request

from typer.testing import CliRunner

from codegraph.cli import app

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def test_serve_is_documented_in_cli_help():
    runner = CliRunner()
    top = runner.invoke(app, ["--help"])
    assert "serve" in top.output
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    # Typer forces ANSI styling under GITHUB_ACTIONS/FORCE_COLOR at import time.
    output = ANSI_ESCAPE.sub("", result.output)
    for text in ("--db", "--port", "--host", "read-only"):
        assert text in output


def test_serve_exits_with_error_for_missing_db(tmp_path):
    result = CliRunner().invoke(app, ["serve", "--db", str(tmp_path / "nope.duckdb")])
    assert result.exit_code != 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_listening(proc: subprocess.Popen, port: int, timeout: float = 30.0) -> None:
    """Block until `port` accepts connections: bounded by `timeout`, and fails fast if the server exits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            pass
        try:  # the pause between attempts; returns early (and fails) if the process died
            code = proc.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            continue
        raise AssertionError(f"serve exited early with code {code}")
    raise AssertionError(f"serve did not listen on port {port} within {timeout}s")


def test_serve_process_answers_root_and_stats(indexed_db):
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from codegraph.cli import app; app()",
            "serve",
            "--db",
            str(indexed_db),
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_until_listening(proc, port)
        stats = urllib.request.urlopen(f"{base}/api/stats", timeout=10).read()
        assert b"total_nodes" in stats
        assert b"codegraph" in urllib.request.urlopen(f"{base}/").read()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
