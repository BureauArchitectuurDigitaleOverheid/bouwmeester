"""Pydantic schemas for eenheid module toggles."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# Canonical module keys — maps to permission.category groups
ModuleKey = Literal["corpus", "taken", "leads", "initiatieven", "opdrachten"]

VALID_MODULES: set[str] = {"corpus", "taken", "leads", "initiatieven", "opdrachten"}

# Maps module keys to the permission categories they control
MODULE_PERMISSION_CATEGORIES: dict[str, list[str]] = {
    "corpus": ["node", "edge", "tag"],
    "taken": ["task"],
    "leads": ["lead"],
    "initiatieven": ["initiatief"],
    "opdrachten": ["opdracht"],
}

MODULE_LABELS: dict[str, str] = {
    "corpus": "Corpus",
    "taken": "Taken",
    "leads": "Leads",
    "initiatieven": "Initiatieven",
    "opdrachten": "Opdrachten",
}


class EenheidModuleResponse(BaseModel):
    module: str
    enabled: bool
    inherited_from: str | None = None
    inherited_from_naam: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EenheidModuleUpdate(BaseModel):
    module: ModuleKey
    enabled: bool


class EenheidModulesResponse(BaseModel):
    eenheid_id: UUID
    modules: list[EenheidModuleResponse]
