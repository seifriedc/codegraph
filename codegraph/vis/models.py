"""Pydantic models: the JSON contract between the vis API and the UI."""
from __future__ import annotations

from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_nodes: int
    total_edges: int
    total_files: int
    nodes_by_language: dict[str, int]
    nodes_by_kind: dict[str, int]
    edges_by_kind: dict[str, int]
