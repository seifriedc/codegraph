from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from tree_sitter import Language, Parser, Query, QueryCursor, QueryError


@dataclass
class ASTMatch:
    file: Path
    pattern_index: int
    captures: dict[str, list[tuple[str, int, int]]]  # name → [(text, line, col), ...]


def _get_registry() -> dict[str, tuple[Language, Parser]]:
    from codegraph.parsers.ada_parser import _LANGUAGE as ADA_L, _PARSER as ADA_P
    from codegraph.parsers.c_parser import _LANGUAGE as C_L, _PARSER as C_P
    from codegraph.parsers.cpp_parser import _LANGUAGE as CPP_L, _PARSER as CPP_P

    return {"ada": (ADA_L, ADA_P), "c": (C_L, C_P), "cpp": (CPP_L, CPP_P)}


def resolve_files(path: Path | None, db: Path | None) -> list[Path]:
    """Return source files to search, from DB file list or directory walk."""
    from codegraph.parsers import detect_language

    if db is not None and db.exists():
        import duckdb

        conn = duckdb.connect(str(db), read_only=True)
        rows = conn.execute(
            "SELECT DISTINCT file_path FROM nodes WHERE kind = 'file'"
        ).fetchall()
        conn.close()
        return sorted(Path(r[0]) for r in rows if Path(r[0]).exists())

    root = path or Path(".")
    return sorted(p for p in root.rglob("*") if p.is_file() and detect_language(p) is not None)


def query_files(
    pattern: str,
    files: list[Path],
    language: str | None = None,
    verbose: bool = False,
) -> Iterator[ASTMatch]:
    """Run a tree-sitter S-expression pattern across source files, yielding matches."""
    from codegraph.parsers import detect_language

    registry = _get_registry()

    compiled: dict[str, Query] = {}
    compile_errors: dict[str, str] = {}
    for lang_name, (lang_obj, _) in registry.items():
        if language and lang_name != language:
            continue
        try:
            compiled[lang_name] = Query(lang_obj, pattern)
        except QueryError as exc:
            compile_errors[lang_name] = str(exc)
            if verbose:
                print(f"[skip {lang_name}: {exc}]", file=sys.stderr)

    if not compiled:
        if compile_errors:
            msgs = "; ".join(f"{lang}: {msg}" for lang, msg in compile_errors.items())
            raise ValueError(f"Pattern rejected by all targeted languages — {msgs}")
        return

    for path in files:
        file_lang = detect_language(path)
        if file_lang not in compiled:
            continue
        _, parser = registry[file_lang]
        source = path.read_bytes()
        tree = parser.parse(source)
        cursor = QueryCursor(compiled[file_lang])

        for pat_idx, cap_nodes in cursor.matches(tree.root_node):
            captures: dict[str, list[tuple[str, int, int]]] = {}
            for cap_name, nodes in cap_nodes.items():
                entries = []
                for node in nodes:
                    text = (node.text or b"").decode("utf-8", errors="replace")
                    first_line = text.split("\n", 1)[0]
                    if len(text) > len(first_line):
                        first_line += " ..."
                    entries.append((first_line, node.start_point.row + 1, node.start_point.column))
                captures[cap_name] = entries
            yield ASTMatch(file=path, pattern_index=pat_idx, captures=captures)


def format_match(m: ASTMatch) -> str:
    """Format a match for text output."""
    if not m.captures:
        return f"{m.file}: (match with no captures)"

    lines = []
    cap_names = sorted(m.captures)
    primary = cap_names[0]
    p_text, p_line, p_col = m.captures[primary][0]
    lines.append(f"{m.file}:{p_line}:{p_col}  @{primary}  {p_text!r}")

    for name in cap_names[1:]:
        for text, line, col in m.captures[name]:
            lines.append(f"    @{name}  {line}:{col}  {text!r}")

    return "\n".join(lines)


def dump_ast(path: Path, named_only: bool = False) -> str:
    """Return a text representation of the full AST for a source file."""
    from codegraph.parsers import detect_language

    lang = detect_language(path)
    if lang is None:
        raise ValueError(f"unsupported file type: {path.suffix!r}")

    registry = _get_registry()
    if lang not in registry:
        raise ValueError(f"no parser registered for language: {lang!r}")

    _, parser = registry[lang]
    source = path.read_bytes()
    tree = parser.parse(source)

    lines: list[str] = []
    _dump_node(tree.root_node, 0, named_only, lines)
    return "\n".join(lines)


def _dump_node(node, depth: int, named_only: bool, out: list[str]) -> None:
    if named_only and not node.is_named:
        return

    sp = node.start_point
    ep = node.end_point
    loc = f"[{sp.row}:{sp.column} - {ep.row}:{ep.column}]"
    indent = "  " * depth

    if node.child_count == 0:
        text = (node.text or b"").decode("utf-8", errors="replace")
        out.append(f"{indent}{node.type} {loc} {text!r}")
    else:
        out.append(f"{indent}{node.type} {loc}")
        for child in node.children:
            _dump_node(child, depth + 1, named_only, out)


def _read_pattern() -> str | None:
    """Read one S-expression pattern, spanning multiple lines if parens are unbalanced.

    Multi-line patterns are consolidated into a single readline history entry so
    that pressing up-arrow replays the whole pattern, not individual lines.
    """
    try:
        import readline as _rl
        history_start = _rl.get_current_history_length()
    except ImportError:
        _rl = None  # type: ignore[assignment]
        history_start = 0

    try:
        buf = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    # A meta-command or empty input — return immediately without reading more lines.
    if not buf or buf.startswith(":"):
        return buf

    while buf.count("(") > buf.count(")"):
        try:
            cont = input("... ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if cont:
            buf += " " + cont

    if _rl is not None:
        # Replace the individually-added lines with the assembled pattern as one entry.
        current_len = _rl.get_current_history_length()
        for i in range(current_len - 1, history_start - 1, -1):
            _rl.remove_history_item(i)
        _rl.add_history(buf)

    return buf


def run_repl(
    files: list[Path],
    language: str | None = None,
    verbose: bool = False,
) -> None:
    """Interactive REPL for running AST queries."""
    try:
        import readline  # noqa: F401 — enables line editing/history as side effect
    except ImportError:
        pass

    lang_display = language or "all"
    print(f"codegraph ast shell  |  {len(files)} file(s)  |  language: {lang_display}")
    print("Enter an S-expression pattern, or :help for commands.\n")

    lang_filter = language
    json_mode = False

    while True:
        pattern = _read_pattern()
        if pattern is None:
            break

        if not pattern:
            continue

        if pattern.startswith(":"):
            parts = pattern[1:].split()
            cmd = parts[0].lower()
            if cmd in ("quit", "q", "exit"):
                break
            elif cmd == "help":
                _print_repl_help()
            elif cmd == "lang":
                if len(parts) > 1:
                    lang_filter = parts[1]
                    print(f"Language filter: {lang_filter}")
                else:
                    lang_filter = None
                    print("Language filter cleared (all languages)")
            elif cmd == "files":
                for f in files:
                    print(f"  {f}")
                print(f"  ({len(files)} total)")
            elif cmd == "json":
                json_mode = not json_mode
                print(f"JSON output: {'on' if json_mode else 'off'}")
            else:
                print(f"Unknown command :{cmd}  (try :help)")
        else:
            try:
                matches = list(query_files(pattern, files, language=lang_filter, verbose=verbose))
                if json_mode:
                    import json
                    print(json.dumps([_match_to_dict(m) for m in matches], indent=2))
                else:
                    for m in matches:
                        print(format_match(m))
                count = len(matches)
                print(f"({count} match{'es' if count != 1 else ''})")
            except (QueryError, ValueError) as exc:
                print(f"Query error: {exc}")


def _print_repl_help() -> None:
    print(
        "  :lang <name>   filter to a language (ada, c, cpp); blank clears filter\n"
        "  :files         list files in scope\n"
        "  :json          toggle JSON output\n"
        "  :quit          exit"
    )


def _match_to_dict(m: ASTMatch) -> dict:
    return {
        "file": str(m.file),
        "pattern_index": m.pattern_index,
        "captures": {
            name: [{"text": t, "line": l, "col": c} for t, l, c in entries]
            for name, entries in m.captures.items()
        },
    }
