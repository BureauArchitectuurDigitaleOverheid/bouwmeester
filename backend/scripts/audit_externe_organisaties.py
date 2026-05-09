"""Audit-rapport: bestaande ExterneOrganisatie-rijen vs TOOI-data.

Genereert een rapport per ExterneOrganisatie-rij:
  - exact-match in TOOI op naam? -> markeer als TOOI-merge-kandidaat
  - exact-match op afkorting? -> idem
  - genormaliseerde naam-match? -> idem
  - geen match? -> blijft handmatig

Schrijft het rapport naar stdout en optioneel naar
`backend/scripts/data/externe_org_reconciliation.yaml` (template waar handmatige
reviewer kan beslissen). Rapport is informatief; er gebeurt niks aan de DB.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.externe_organisatie import ExterneOrganisatie
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid


def _normaliseer(naam: str) -> str:
    n = " ".join(naam.lower().split())
    # strip prefixen die TOOI gebruikt (lowercase soort-aanduiding)
    for prefix in (
        "ministerie van ",
        "zbo ",
        "agentschap ",
        "rijksdienst ",
        "stichting ",
        "samenwerkingsorganisatie ",
        "adviescollege ",
        "organisatieonderdeel ",
        "vereniging ",
    ):
        if n.startswith(prefix):
            n = n[len(prefix) :]
    # strip 'gemeente '/'provincie '/'waterschap ' prefix
    n = re.sub(r"^(gemeente|provincie|waterschap)\s+", "", n)
    return n.strip()


@dataclass
class MatchResult:
    externe_id: str
    externe_naam: str
    externe_afkorting: str | None
    externe_type: str
    match_type: str  # exact_naam | exact_afkorting | naam_normalized | geen
    tooi_uri: str | None
    tooi_naam: str | None
    tooi_type: str | None
    confidence: str  # hoog | midden | laag


async def audit(session: AsyncSession) -> list[MatchResult]:
    externes = (await session.execute(select(ExterneOrganisatie))).scalars().all()

    # Bouw indices op TOOI-data
    tooi_rows = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.bron == "tooi",
                    OrganisatieEenheid.geldig_tot.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    by_naam_exact: dict[str, OrganisatieEenheid] = {}
    by_naam_norm: dict[str, list[OrganisatieEenheid]] = {}
    by_afkorting: dict[str, list[OrganisatieEenheid]] = {}
    for r in tooi_rows:
        by_naam_exact[r.naam.lower().strip()] = r
        by_naam_norm.setdefault(_normaliseer(r.naam), []).append(r)
        if r.afkorting:
            by_afkorting.setdefault(r.afkorting.lower(), []).append(r)

    results: list[MatchResult] = []
    for ext in externes:
        match: tuple[str, OrganisatieEenheid | None, str] = ("geen", None, "laag")

        # 1. exact naam (case-insensitive)
        if ext.naam.lower().strip() in by_naam_exact:
            match = ("exact_naam", by_naam_exact[ext.naam.lower().strip()], "hoog")
        # 2. exact afkorting (1 hit -> hoog, meerdere -> midden)
        elif ext.afkorting and ext.afkorting.lower() in by_afkorting:
            kandidaten = by_afkorting[ext.afkorting.lower()]
            conf = "hoog" if len(kandidaten) == 1 else "midden"
            match = ("exact_afkorting", kandidaten[0], conf)
        # 3. genormaliseerde naam
        else:
            norm = _normaliseer(ext.naam)
            if norm in by_naam_norm:
                kandidaten = by_naam_norm[norm]
                conf = "hoog" if len(kandidaten) == 1 else "midden"
                match = ("naam_normalized", kandidaten[0], conf)

        kind, ko, conf = match
        results.append(
            MatchResult(
                externe_id=str(ext.id),
                externe_naam=ext.naam,
                externe_afkorting=ext.afkorting,
                externe_type=ext.type,
                match_type=kind,
                tooi_uri=ko.tooi_uri if ko else None,
                tooi_naam=ko.naam if ko else None,
                tooi_type=ko.type if ko else None,
                confidence=conf if ko else "laag",
            )
        )
    return results


async def main() -> None:
    async with async_session() as session:
        results = await audit(session)

    # Sorteer op match_type voor leesbaarheid
    order = {"exact_naam": 0, "exact_afkorting": 1, "naam_normalized": 2, "geen": 3}
    results.sort(key=lambda r: (order[r.match_type], r.externe_naam))

    print(f"Aantal ExterneOrganisatie: {len(results)}")
    print()
    for r in results:
        if r.match_type == "geen":
            print(
                f"  [GEEN MATCH] {r.externe_naam} ({r.externe_afkorting or '-'}) "
                f"type={r.externe_type}"
            )
        else:
            print(
                f"  [{r.match_type:<16}] {r.externe_naam:40s} "
                f"({r.externe_afkorting or '-':>10s}) -> "
                f"{r.tooi_naam} ({r.tooi_type}) [{r.confidence}]"
            )


if __name__ == "__main__":
    asyncio.run(main())
