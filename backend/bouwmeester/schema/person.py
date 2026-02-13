"""Pydantic schemas for Person."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

import phonenumbers
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

PHONE_LABELS = {"werk": "Werk", "mobiel": "Mobiel", "prive": "Priv\u00e9"}


class PersonEmailCreate(BaseModel):
    email: EmailStr
    is_default: bool = False


class PersonEmailResponse(BaseModel):
    id: UUID
    email: str
    is_default: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PersonPhoneCreate(BaseModel):
    phone_number: str = Field(min_length=3, max_length=50)
    label: str = Field(max_length=20)
    is_default: bool = False

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, v: str) -> str:
        """Parse and normalize to E.164 international format."""
        try:
            parsed = phonenumbers.parse(v, "NL")  # default region NL
        except phonenumbers.NumberParseException as exc:
            raise ValueError(f"Ongeldig telefoonnummer: {exc}") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Ongeldig telefoonnummer")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class PersonPhoneResponse(BaseModel):
    id: UUID
    phone_number: str
    label: str
    is_default: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PersonBase(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    email: str | None = Field(None, max_length=254)
    functie: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    is_agent: bool = False


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    naam: str | None = Field(None, min_length=1, max_length=200)
    email: str | None = Field(None, max_length=254)
    functie: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    is_agent: bool | None = None


class PersonResponse(PersonBase):
    """Response schema for person lists — api_key excluded for security."""

    id: UUID
    is_active: bool
    is_agent: bool
    is_admin: bool
    created_at: datetime
    emails: list[PersonEmailResponse] = []
    phones: list[PersonPhoneResponse] = []
    default_email: str | None = None
    default_phone: str | None = None
    has_api_key: bool = False

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _handle_unloaded_relations(cls, data):
        """Set empty defaults for unloaded email/phone relationships on ORM objects.

        When a Person is fetched without ``selectinload(Person.emails)``
        or ``selectinload(Person.phones)``, accessing those attributes
        would trigger a lazy load which fails in async context
        (MissingGreenlet).  We detect this via the SQLAlchemy instance
        state and replace the unloaded attributes with safe defaults so
        Pydantic never touches the lazy attribute.
        """
        if not hasattr(data, "__tablename__"):
            return data

        from sqlalchemy.orm.attributes import instance_state

        state = instance_state(data)
        loaded = state.dict

        if "emails" not in loaded:
            # Pydantic will read the ORM attr → MissingGreenlet.
            # Build a dict from all loaded column attrs, then override
            # the unloaded relationship attrs with safe defaults.
            result = {k: v for k, v in loaded.items() if not k.startswith("_")}
            result["emails"] = []
            result["phones"] = []
            result["default_email"] = data.email
            result["default_phone"] = None
            return result

        return data


class PersonDetailResponse(PersonResponse):
    """Full response for a single person."""

    pass


class ApiKeyResponse(BaseModel):
    """Returned after key rotation (one-time display)."""

    api_key: str
    person_id: UUID


class PersonCreateResponse(PersonDetailResponse):
    """Returned after creating a person.

    For agents, ``api_key`` contains the one-time plaintext key.
    For non-agents, ``api_key`` is always ``None``.
    This is the **only** response type that ever carries the plaintext key.
    """

    api_key: str | None = None


class NodeStakeholderCreate(BaseModel):
    person_id: UUID
    rol: str


class NodeStakeholderUpdate(BaseModel):
    rol: str


class NodeStakeholderResponse(BaseModel):
    id: UUID
    person: PersonResponse
    rol: str

    model_config = ConfigDict(from_attributes=True)


class PersonTaskSummary(BaseModel):
    id: UUID
    title: str
    status: str
    priority: str
    due_date: date | None = Field(None, validation_alias="deadline")

    model_config = ConfigDict(from_attributes=True)


class PersonStakeholderNode(BaseModel):
    node_id: UUID
    node_title: str
    node_type: str
    stakeholder_rol: str


class PersonSummaryResponse(BaseModel):
    open_task_count: int
    done_task_count: int
    open_tasks: list[PersonTaskSummary]
    stakeholder_nodes: list[PersonStakeholderNode]


Dienstverband = Literal["in_dienst", "ingehuurd", "extern"]


class OnboardingRequest(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    functie: str = Field(min_length=1, max_length=200)
    organisatie_eenheid_id: UUID
    dienstverband: Dienstverband = "in_dienst"


class PersonOrganisatieCreate(BaseModel):
    organisatie_eenheid_id: UUID
    dienstverband: Dienstverband = "in_dienst"
    start_datum: date


class PersonOrganisatieUpdate(BaseModel):
    dienstverband: Dienstverband | None = None
    eind_datum: date | None = None


class PersonOrganisatieResponse(BaseModel):
    id: UUID
    person_id: UUID
    organisatie_eenheid_id: UUID
    organisatie_eenheid_naam: str
    dienstverband: str
    start_datum: date
    eind_datum: date | None = None
