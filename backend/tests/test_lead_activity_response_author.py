"""Tests dat LeadActivityResponse de auteur-naam vult uit de relationship.

Latente bug die zichtbaar werd toen Mattermost-imports leidden tot notes
zonder zichtbare auteur in de UI: het schema-veld ``author_naam`` bestond,
maar werd nergens gevuld.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from bouwmeester.schema.lead import LeadActivityResponse


class _StubAuthor:
    def __init__(self, naam: str) -> None:
        self.naam = naam


def _orm_stub(*, author=None, author_id=None):
    """Mimic an ORM LeadActivity instance with the attributes the schema reads."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        author_id=author_id,
        author=author,
        content="hello",
        activity_type="note",
        metadata_={},
        uitkomst=None,
        vervolgacties=None,
        created_at=datetime.now(UTC),
    )


def test_author_naam_filled_from_relationship():
    obj = _orm_stub(author=_StubAuthor("Anne Schuth"), author_id=uuid.uuid4())
    resp = LeadActivityResponse.model_validate(obj)
    assert resp.author_naam == "Anne Schuth"


def test_no_author_keeps_naam_none():
    obj = _orm_stub(author=None, author_id=None)
    resp = LeadActivityResponse.model_validate(obj)
    assert resp.author_naam is None


def test_existing_naam_is_not_overwritten():
    # Defensive: if a caller pre-fills author_naam, we shouldn't clobber it.
    obj = _orm_stub(author=_StubAuthor("From Relationship"), author_id=uuid.uuid4())
    obj.author_naam = "Pre-filled"
    resp = LeadActivityResponse.model_validate(obj)
    assert resp.author_naam == "Pre-filled"
