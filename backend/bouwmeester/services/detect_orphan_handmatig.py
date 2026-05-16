"""Detect handmatige rijen die alsnog matchen op een TOOI-rij.

After the ExterneOrganisatie elimination migration, FCC-imports zonder
YAML-entry zijn als bron='handmatig' onder de "Marktpartijen en overige"
synthetische groep beland — ook als er een TOOI-rij met dezelfde
afkorting of naam bestaat. Voorbeeld: CJIB. De FCC had naam 'CJIB',
TOOI heeft 'Centraal Justitieel Incassobureau' met afkorting 'CJIB'.

Deze service zoekt zulke duplicaten op en maakt PendingReconciliation-
rijen aan zodat de admin ze via Beheer > Reconciliatie kan mergen
met dezelfde merge_organisatie_eenheden() helper.

Match-strategie (in volgorde, eerste hit wint):
  1. afkorting case-insensitive exact (sterkst — 'CJIB' = 'CJIB')
  2. genormaliseerde naam (lower + trim + strip 'ministerie van' / 'agentschap')

Kandidaten komen uit alle gesyncte bronnen (tooi, organogram_scrape,
kabinet, ...), niet alleen TOOI. De DGDOO-duplicaat ontstond doordat een
seed-DG ('DG Digitalisering en Overheidsorganisatie') en een
organogram-scrape-rij ('Digitalisering en Overheidsorganisatie') naast
elkaar bleven staan; een tooi-only kandidaatfilter zag dat nooit.

Skipt rijen die al een open reconciliation hebben.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.text import normalize_org_name
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation

log = logging.getLogger(__name__)

# Bronnen waaruit een kandidaat voor een handmatige rij mag komen. Alles
# wat door een externe sync wordt onderhouden; 'handmatig' zelf valt af
# (we willen een handmatige rij juist in een gesyncte rij opgaan).
_KANDIDAAT_BRONNEN = (
    "tooi",
    "organogram_scrape",
    "kabinet",
    "rio",
    "ministeries_csv",
)


@dataclass
class OrphanScanStats:
    scanned: int
    found_match: int
    new_reconciliations: int
    already_pending: int


async def _existing_open_for_handmatig(
    session: AsyncSession, handmatig_id: uuid.UUID
) -> PendingReconciliation | None:
    return (
        await session.execute(
            select(PendingReconciliation).where(
                PendingReconciliation.handmatige_id == handmatig_id,
                PendingReconciliation.status == "open",
            )
        )
    ).scalar_one_or_none()


async def detect_orphan_handmatig_matches(
    session: AsyncSession, *, commit: bool = True
) -> OrphanScanStats:
    """Scan handmatige rijen op kandidaat-TOOI-matches.

    Doelgroep: rijen met bron='handmatig' die geen tooi_uri hebben.
    Voor elke rij wordt gezocht naar TOOI-kandidaten op afkorting (CI)
    of genormaliseerde naam. Bij een hit komt er een
    PendingReconciliation-rij. Reeds open reconciliations worden
    overgeslagen.
    """
    handmatig_rows = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.bron == "handmatig",
                    OrganisatieEenheid.tooi_uri.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    stats = OrphanScanStats(
        scanned=len(handmatig_rows),
        found_match=0,
        new_reconciliations=0,
        already_pending=0,
    )

    for handmatig in handmatig_rows:
        afk = (handmatig.afkorting or "").strip()
        norm = normalize_org_name(handmatig.naam)
        if not afk and not norm:
            continue

        # Bouw query: afkorting CI exact OR naam ILIKE (om kandidaten
        # met dezelfde 'kern' op te halen). Definitieve match-check op
        # genormaliseerde naam doen we daarna in Python omdat de
        # prefix-stripping niet in SQL is uit te drukken.
        conditions = []
        if afk:
            conditions.append(OrganisatieEenheid.afkorting.ilike(afk))
        if norm:
            # ILIKE %norm% pakt 'agentschap X', 'DG X', 'X (AFK)' etc. zonder
            # dat we vooraf alle prefix-varianten hoeven op te sommen.
            conditions.append(OrganisatieEenheid.naam.ilike(f"%{norm}%"))

        if not conditions:
            continue

        kandidaten = (
            (
                await session.execute(
                    select(OrganisatieEenheid).where(
                        and_(
                            OrganisatieEenheid.bron.in_(_KANDIDAAT_BRONNEN),
                            OrganisatieEenheid.id != handmatig.id,
                            or_(*conditions),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        # Afkorting wint van naam-match — minder vals-positief.
        kandidaat: OrganisatieEenheid | None = None
        match_reden = ""
        if afk:
            for kand in kandidaten:
                if (kand.afkorting or "").strip().lower() == afk.lower():
                    kandidaat = kand
                    match_reden = "afkorting_ci"
                    break
        if kandidaat is None and norm:
            for kand in kandidaten:
                if normalize_org_name(kand.naam) == norm:
                    kandidaat = kand
                    match_reden = "naam_normalized"
                    break

        if kandidaat is None:
            continue

        stats.found_match += 1

        existing = await _existing_open_for_handmatig(session, handmatig.id)
        if existing is not None:
            stats.already_pending += 1
            continue

        rec = PendingReconciliation(
            id=uuid.uuid4(),
            resource_type="organisatie_eenheid",
            handmatige_id=handmatig.id,
            kandidaat_id=kandidaat.id,
            kandidaat_bron=kandidaat.bron or "tooi",
            match_reden=match_reden,
            status="open",
        )
        session.add(rec)
        stats.new_reconciliations += 1
        log.info(
            "Orphan-match: handmatig %s '%s' (afk=%s) -> %s %s '%s' (%s)",
            handmatig.id,
            handmatig.naam,
            handmatig.afkorting,
            kandidaat.bron,
            kandidaat.id,
            kandidaat.naam,
            match_reden,
        )

    if commit:
        await session.commit()
    else:
        await session.flush()
    return stats
