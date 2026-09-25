"""Check the attachment tables against the bijlagen store.

Every row in ``bron_bijlage``, ``chat_attachment`` and ``lead_attachment``
names a file. This counts, per table, how many of those files the store
actually has. ``GET /api/admin/bijlagen/opslag`` serves it.

It started as the gate for moving the files off the old volume into object
storage; it stays as the way to see that the database and the bucket agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.blob_store import BlobStore, InvalidKeyError

# How many missing keys a report names; the count is always complete.
_MAX_LISTED = 20


@dataclass
class TableCheck:
    """One attachment table against the store."""

    table: str
    total: int = 0
    present: int = 0
    missing_count: int = 0
    missing: list[str] = field(default_factory=list)


async def check_database_against_store(
    session: AsyncSession, store: BlobStore
) -> list[TableCheck]:
    """For each attachment table, how many of its files *store* actually has."""
    from bouwmeester.core.storage import chat_key
    from bouwmeester.models.bron_bijlage import BronBijlage
    from bouwmeester.models.chat_attachment import ChatAttachment
    from bouwmeester.models.lead_attachment import LeadAttachment

    sources = [
        ("bron_bijlage", select(BronBijlage.pad), lambda pad: pad),
        ("chat_attachment", select(ChatAttachment.pad), chat_key),
        (
            "lead_attachment",
            select(LeadAttachment.pad).where(LeadAttachment.pad.is_not(None)),
            lambda pad: pad,
        ),
    ]
    checks: list[TableCheck] = []
    for table, stmt, to_key in sources:
        check = TableCheck(table=table)
        for pad in (await session.execute(stmt)).scalars():
            check.total += 1
            key = to_key(pad)
            try:
                found = await store.size(key) is not None
            except InvalidKeyError:
                found = False
            if found:
                check.present += 1
            else:
                check.missing_count += 1
                if len(check.missing) < _MAX_LISTED:
                    check.missing.append(key)
        checks.append(check)
    return checks
