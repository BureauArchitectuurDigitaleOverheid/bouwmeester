"""Lezen en schrijven van de signaalcontext per scope."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.signaalcontext import (
    MAX_TEKST,
    Signaalcontext,
)


class SignaalcontextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, scope_type: str, scope_id: uuid.UUID
    ) -> Signaalcontext | None:
        stmt = select(Signaalcontext).where(
            Signaalcontext.scope_type == scope_type,
            Signaalcontext.scope_id == scope_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def tekst_voor(self, scope_type: str, scope_id: uuid.UUID) -> str | None:
        """Alleen de tekst, voor de prompts."""
        rij = await self.get(scope_type, scope_id)
        return rij.tekst if rij is not None else None

    async def zet(
        self, scope_type: str, scope_id: uuid.UUID, tekst: str
    ) -> Signaalcontext | None:
        """Schrijf de tekst, of verwijder hem als hij leeg is.

        Leeg opslaan zou een rij achterlaten die niets zegt maar wel in
        elke prompt een lege regel oplevert; weghalen is hetzelfde
        resultaat zonder die rij.
        """
        tekst = (tekst or "").strip()[:MAX_TEKST]
        bestaand = await self.get(scope_type, scope_id)

        if not tekst:
            if bestaand is not None:
                await self.session.delete(bestaand)
            return None

        if bestaand is None:
            bestaand = Signaalcontext(
                scope_type=scope_type, scope_id=scope_id, tekst=tekst
            )
            self.session.add(bestaand)
        else:
            bestaand.tekst = tekst
        return bestaand
