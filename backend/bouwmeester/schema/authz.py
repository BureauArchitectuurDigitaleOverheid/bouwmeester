"""Schemas for the AuthZEN-shaped evaluation endpoint (``/api/authz``)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bouwmeester.core.authz import RESOURCE_TYPES

MAX_EVALUATIONS = 50

# "role" only appears in the grant action ``role:assign``.
EVALUATION_RESOURCE_TYPES = RESOURCE_TYPES | {"role"}


class AuthzResourceProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # For a resource that does not exist yet: the eenheid it would go into.
    eenheid_id: UUID | None = None
    # "Is there any eenheid where I may create this?" (generic create buttons).
    anywhere: bool = False
    # Grant actions: the rol or role handed out, and to whom (omitted: to
    # someone other than the caller).
    rol: str | None = Field(default=None, max_length=50)
    role_id: str | None = Field(default=None, max_length=50)
    target_person_id: UUID | None = None


class AuthzResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: UUID | None = None
    properties: AuthzResourceProperties | None = None

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in EVALUATION_RESOURCE_TYPES:
            raise ValueError(f"Onbekend resource-type: {value}")
        return value


class AuthzEvaluation(BaseModel):
    # No subject: the subject is always the caller.
    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern=r"^[a-z_]+:[a-z_]+$", max_length=100)
    resource: AuthzResource


class AuthzEvaluationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[AuthzEvaluation] = Field(min_length=1, max_length=MAX_EVALUATIONS)


class AuthzDecision(BaseModel):
    decision: bool


class AuthzEvaluationsResponse(BaseModel):
    evaluations: list[AuthzDecision]
