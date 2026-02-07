"""Pydantic schemas for import/export operations."""

from pydantic import BaseModel


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


class ExportMeta(BaseModel):
    total_nodes: int
    total_edges: int
    total_edge_types: int
