"""Repository voor ParlementairAbonnement en ParlementairTreffer."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.parlementair_treffer import ParlementairTreffer


class ParlementairAbonnementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, abonnement_id: UUID) -> ParlementairAbonnement | None:
        return await self.session.get(ParlementairAbonnement, abonnement_id)

    async def get_by_term(
        self, scope_type: str, scope_id: UUID, term: str
    ) -> ParlementairAbonnement | None:
        """Zoek binnen een scope op de genormaliseerde vorm.

        'RegelRecht' en 'regelrecht' zijn hetzelfde abonnement.
        """
        stmt = select(ParlementairAbonnement).where(
            ParlementairAbonnement.scope_type == scope_type,
            ParlementairAbonnement.scope_id == scope_id,
            ParlementairAbonnement.term_genormaliseerd
            == ParlementairAbonnement.normaliseer(term),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_scope(
        self, scope_type: str, scope_id: UUID, *, alleen_actief: bool = False
    ) -> list[ParlementairAbonnement]:
        stmt = select(ParlementairAbonnement).where(
            ParlementairAbonnement.scope_type == scope_type,
            ParlementairAbonnement.scope_id == scope_id,
        )
        if alleen_actief:
            stmt = stmt.where(ParlementairAbonnement.actief.is_(True))
        stmt = stmt.order_by(ParlementairAbonnement.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_actief(self) -> list[ParlementairAbonnement]:
        """Alle actieve abonnementen, voor de poll-ronde.

        De poller zoekt per unieke term, niet per abonnement: twee
        initiatieven die dezelfde term volgen leveren één zoekopdracht op.
        """
        stmt = select(ParlementairAbonnement).where(
            ParlementairAbonnement.actief.is_(True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        scope_type: str,
        scope_id: UUID,
        term: str,
        is_frase: bool = True,
        notitie: str | None = None,
        created_by_id: UUID | None = None,
    ) -> ParlementairAbonnement:
        abonnement = ParlementairAbonnement(
            scope_type=scope_type,
            scope_id=scope_id,
            term=term.strip().strip('"'),
            term_genormaliseerd=ParlementairAbonnement.normaliseer(term),
            is_frase=is_frase,
            notitie=notitie,
            created_by_id=created_by_id,
        )
        self.session.add(abonnement)
        await self.session.flush()
        await self.session.refresh(abonnement)
        return abonnement

    async def delete(self, abonnement: ParlementairAbonnement) -> None:
        await self.session.delete(abonnement)
        await self.session.flush()

    async def registreer_treffers(
        self, parlementair_item_id: UUID, abonnement_ids: list[UUID]
    ) -> int:
        """Leg vast welke abonnementen dit item aandroegen.

        ON CONFLICT DO NOTHING: een item kan bij een herhaalde ronde opnieuw
        langskomen terwijl de koppeling al bestaat. Dat is geen fout.
        Geeft terug hoeveel koppelingen nieuw waren.
        """
        if not abonnement_ids:
            return 0

        stmt = (
            pg_insert(ParlementairTreffer)
            .values(
                [
                    {
                        "parlementair_item_id": parlementair_item_id,
                        "abonnement_id": aid,
                    }
                    for aid in abonnement_ids
                ]
            )
            .on_conflict_do_nothing(constraint="uq_treffer_item_abonnement")
            # Geef de abonnement-ids terug, niet de treffer-ids: alleen de
            # rijen die er echt bij kwamen mogen meetellen. Ophogen over de
            # volledige `abonnement_ids` zou een abonnement dat dit item al
            # had nogmaals tellen, en dan lopen `treffers_totaal` en de
            # COUNT(*) uit `telling_per_abonnement` uiteen.
            .returning(ParlementairTreffer.abonnement_id)
        )
        result = await self.session.execute(stmt)
        nieuwe_ids = list(result.scalars().all())

        if nieuwe_ids:
            now = datetime.now(UTC)
            for aid in nieuwe_ids:
                abonnement = await self.session.get(ParlementairAbonnement, aid)
                if abonnement is not None:
                    abonnement.laatste_treffer_op = now
                    abonnement.treffers_totaal += 1
            await self.session.flush()
        return len(nieuwe_ids)

    async def list_abonnementen_voor_item(
        self, parlementair_item_id: UUID
    ) -> list[ParlementairAbonnement]:
        """Welke termen droegen dit item aan (voor het bericht)."""
        stmt = (
            select(ParlementairAbonnement)
            .join(
                ParlementairTreffer,
                ParlementairTreffer.abonnement_id == ParlementairAbonnement.id,
            )
            .where(ParlementairTreffer.parlementair_item_id == parlementair_item_id)
            .order_by(ParlementairAbonnement.term.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def markeer_weggeklikt(self, parlementair_item_id: UUID) -> None:
        """Tel een 'niet relevant' bij elke term die dit item aandroeg.

        Nooit automatisch deactiveren: bij recall-over-precisie is een
        weggeklikte treffer normaal, en een term die zichzelf uitzet zou
        stil dekkingsverlies opleveren. Het getal is een signaal voor de
        gebruiker op de initiatief-pagina.
        """
        abonnementen = await self.list_abonnementen_voor_item(parlementair_item_id)
        for abonnement in abonnementen:
            abonnement.weggeklikt_totaal += 1
        await self.session.flush()

    async def telling_per_abonnement(
        self, scope_type: str, scope_id: UUID
    ) -> dict[UUID, int]:
        """Aantal treffers per abonnement binnen een scope."""
        stmt = (
            select(ParlementairAbonnement.id, func.count(ParlementairTreffer.id))
            .outerjoin(
                ParlementairTreffer,
                ParlementairTreffer.abonnement_id == ParlementairAbonnement.id,
            )
            .where(
                ParlementairAbonnement.scope_type == scope_type,
                ParlementairAbonnement.scope_id == scope_id,
            )
            .group_by(ParlementairAbonnement.id)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
