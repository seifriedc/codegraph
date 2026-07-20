from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from codegraph.cli import app
from codegraph.ast_query import dump_ast, query_files, resolve_files

FIXTURES = Path(__file__).parent / "fixtures"
ADA_FILE = FIXTURES / "ada" / "geometry.adb"
C_FILE = FIXTURES / "c" / "math_utils.c"
CPP_FILE = FIXTURES / "cpp" / "shapes.cpp"

runner = CliRunner()


# ---------------------------------------------------------------------------
# dump_ast
# ---------------------------------------------------------------------------


class TestDumpAst:
    def test_ada_contains_root_node(self):
        out = dump_ast(ADA_FILE)
        assert "compilation" in out
        assert "subprogram_body" in out

    def test_c_contains_function_definition(self):
        out = dump_ast(C_FILE)
        assert "function_definition" in out

    def test_named_only_excludes_anonymous(self):
        full = dump_ast(ADA_FILE, named_only=False)
        named = dump_ast(ADA_FILE, named_only=True)
        # Anonymous keywords (e.g. 'with', 'is') appear in full but not named-only
        assert len(full) > len(named)

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "hello.rs"
        f.write_text("fn main() {}")
        with pytest.raises(ValueError, match="unsupported file type"):
            dump_ast(f)

    def test_cli_dump(self):
        result = runner.invoke(app, ["ast", "dump", str(ADA_FILE)])
        assert result.exit_code == 0
        assert "compilation" in result.output
        assert "subprogram_body" in result.output

    def test_cli_dump_named_only(self):
        result = runner.invoke(app, ["ast", "dump", str(ADA_FILE), "--named-only"])
        assert result.exit_code == 0
        full = runner.invoke(app, ["ast", "dump", str(ADA_FILE)]).output
        assert len(result.output) < len(full)

    def test_cli_dump_bad_file(self, tmp_path):
        f = tmp_path / "hello.rs"
        f.write_text("fn main() {}")
        result = runner.invoke(app, ["ast", "dump", str(f)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# query_files
# ---------------------------------------------------------------------------


class TestQueryFiles:
    def test_ada_subprogram_body(self):
        matches = list(query_files("(subprogram_body) @fn", [ADA_FILE]))
        assert len(matches) >= 2
        names = [m.captures["fn"][0][0] for m in matches]
        assert any("Distance" in n for n in names)
        assert any("Translate" in n for n in names)

    def test_captures_dict_populated(self):
        pattern = (
            "(subprogram_body"
            " (function_specification (identifier) @name)) @body"
        )
        matches = list(query_files(pattern, [ADA_FILE]))
        assert matches
        first = matches[0]
        assert "body" in first.captures
        assert "name" in first.captures
        assert first.captures["name"][0][0] == "Distance"

    def test_c_function_definition(self):
        matches = list(query_files("(function_definition) @fn", [C_FILE]))
        assert len(matches) >= 2

    def test_language_filter_restricts_files(self):
        all_files = [ADA_FILE, C_FILE, CPP_FILE]
        ada_matches = list(query_files("(subprogram_body) @fn", all_files, language="ada"))
        for m in ada_matches:
            assert m.file.suffix in (".adb", ".ads")

    def test_invalid_pattern_skips_gracefully(self):
        # Pattern valid for C but not Ada — should still return C results
        pattern = "(function_definition) @fn"
        matches = list(query_files(pattern, [ADA_FILE, C_FILE]))
        files_hit = {m.file for m in matches}
        assert C_FILE in files_hit
        assert ADA_FILE not in files_hit

    def test_no_matches_returns_empty(self):
        matches = list(query_files("(subprogram_body) @fn", [C_FILE]))
        assert matches == []

    def test_match_line_numbers_are_one_based(self):
        matches = list(query_files("(subprogram_body) @fn", [ADA_FILE]))
        for m in matches:
            for entries in m.captures.values():
                for _, line, _ in entries:
                    assert line >= 1

    def test_multiline_node_text_truncated(self):
        matches = list(query_files("(subprogram_body) @fn", [ADA_FILE]))
        for m in matches:
            for entries in m.captures.values():
                for text, _, _ in entries:
                    assert "\n" not in text


# ---------------------------------------------------------------------------
# resolve_files
# ---------------------------------------------------------------------------


class TestResolveFiles:
    def test_walk_directory(self):
        files = resolve_files(FIXTURES, None)
        suffixes = {f.suffix for f in files}
        assert ".adb" in suffixes
        assert ".c" in suffixes
        assert ".cpp" in suffixes

    def test_ignores_unsupported_extensions(self):
        files = resolve_files(FIXTURES, None)
        for f in files:
            assert f.suffix in (".adb", ".ads", ".c", ".h", ".cc", ".cpp",
                                ".cxx", ".hh", ".hpp", ".hxx", ".py")

    def test_nonexistent_db_falls_back_to_walk(self, tmp_path):
        files = resolve_files(FIXTURES, tmp_path / "no.db")
        assert len(files) > 0


# ---------------------------------------------------------------------------
# CLI query command
# ---------------------------------------------------------------------------


class TestCliQuery:
    def test_basic_query(self):
        result = runner.invoke(app, [
            "ast", "query", "(subprogram_body) @fn", str(FIXTURES),
        ])
        assert result.exit_code == 0
        assert "geometry.adb" in result.output
        assert "@fn" in result.output

    def test_cross_language_query(self):
        result = runner.invoke(app, [
            "ast", "query", "(function_definition) @fn", str(FIXTURES),
        ])
        assert result.exit_code == 0
        assert "math_utils.c" in result.output
        assert "shapes.cpp" in result.output

    def test_language_filter(self):
        result = runner.invoke(app, [
            "ast", "query", "(function_definition) @fn", str(FIXTURES),
            "--language", "c",
        ])
        assert result.exit_code == 0
        assert "math_utils.c" in result.output
        assert "shapes.cpp" not in result.output

    def test_json_output(self):
        import json
        result = runner.invoke(app, [
            "ast", "query", "(subprogram_body) @fn", str(FIXTURES), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert all("file" in item and "captures" in item for item in data)

    def test_verbose_shows_skip_messages(self, capsys):
        result = runner.invoke(app, [
            "ast", "query", "(subprogram_body) @fn", str(FIXTURES), "--verbose",
        ])
        assert result.exit_code == 0
        assert "[skip" in result.output

    def test_no_files_exits_nonzero(self, tmp_path):
        result = runner.invoke(app, [
            "ast", "query", "(subprogram_body) @fn", str(tmp_path),
        ])
        assert result.exit_code == 1
