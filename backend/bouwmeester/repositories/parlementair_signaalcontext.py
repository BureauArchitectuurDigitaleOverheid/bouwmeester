"""Lezen en schrijven van de signaalcontext per scope."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.parlementair_signaalcontext import (
    MAX_TEKST,
    ParlementairSignaalcontext,
)


class ParlementairSignaalcontextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self, scope_type: str, scope_id: uuid.UUID
    ) -> ParlementairSignaalcontext | None:
        stmt = select(ParlementairSignaalcontext).where(
            ParlementairSignaalcontext.scope_type == scope_type,
            ParlementairSignaalcontext.scope_id == scope_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def tekst_voor(self, scope_type: str, scope_id: uuid.UUID) -> str | None:
        """Alleen de tekst, voor de prompts."""
        rij = await self.get(scope_type, scope_id)
        return rij.tekst if rij is not None else None

    async def zet(
        self, scope_type: str, scope_id: uuid.UUID, tekst: str
    ) -> ParlementairSignaalcontext | None:
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
            bestaand = ParlementairSignaalcontext(
                scope_type=scope_type, scope_id=scope_id, tekst=tekst
            )
            self.session.add(bestaand)
        else:
            bestaand.tekst = tekst
        return bestaand
