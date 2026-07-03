from __future__ import annotations
from pathlib import Path

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".adb": "ada",
    ".ads": "ada",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".py": "python",
}


def detect_language(path: Path) -> str | None:
    return EXTENSION_TO_LANGUAGE.get(path.suffix.lower())
