"""Path relativization: paths are shown relative to the common ancestor of indexed files (ADR 0002).

The root itself comes from `Graph.common_root()`, the single definition shared with the Overview.
"""

from __future__ import annotations

import os
from typing import Callable


def make_relativizer(root: str | None) -> Callable[[str | None], str | None]:
    def rel(path: str | None) -> str | None:
        if path is None or root is None:
            return path
        try:
            r = os.path.relpath(path, root)
        except ValueError:
            return path
        # outside the root only when the first component is exactly `..` (a directory named `..foo` is inside)
        return path if r.split(os.sep)[0] == os.pardir else r.replace(os.sep, "/")

    return rel
