"""Path relativization: paths are shown relative to the common ancestor of indexed files (ADR 0002)."""
from __future__ import annotations

import os
from typing import Callable


def common_root(file_paths: list[str]) -> str | None:
    """Deepest directory containing every given file, or None if there are none."""
    dirs = [os.path.dirname(p) for p in file_paths if p]
    if not dirs:
        return None
    try:
        return os.path.commonpath(dirs)
    except ValueError:  # absolute/relative mix: leave paths alone
        return None


def make_relativizer(root: str | None) -> Callable[[str | None], str | None]:
    def rel(path: str | None) -> str | None:
        if path is None or root is None:
            return path
        try:
            r = os.path.relpath(path, root)
        except ValueError:
            return path
        return path if r.startswith("..") else r.replace(os.sep, "/")

    return rel
