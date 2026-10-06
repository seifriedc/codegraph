from __future__ import annotations
import uuid
from dataclasses import dataclass, field

# Stable namespace for uuid5 — same qualified name always produces the same node ID.
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_DNS


def stable_id(qualified_name: str) -> str:
    """Deterministic ID for a named entity so re-indexing produces the same UUID."""
    return str(uuid.uuid5(_NS, qualified_name))


def random_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Node:
    kind: str  # file | module | package | function | class | method | type | variable
    name: str
    language: str
    id: str = field(default_factory=random_id)
    qualified_name: str | None = None
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Edge:
    kind: str  # imports | calls | defines | contains | inherits | references | instantiates
    source_id: str
    target_id: str
    id: str = ""  # empty -> derived deterministically in __post_init__
    file_path: str | None = None
    line: int | None = None
    col: int | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = stable_id(
                f"edge:{self.kind}:{self.source_id}:{self.target_id}:"
                f"{self.file_path}:{self.line}:{self.col}"
            )
