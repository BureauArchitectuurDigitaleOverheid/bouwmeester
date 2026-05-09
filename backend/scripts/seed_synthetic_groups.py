"""Seed synthetische top-level groepen in OrganisatieEenheid.

Deze synthetische nodes zijn peers van ministeries en dienen als parent voor
TOOI-data die niet onder een ministerie hangt (gemeenten, provincies, etc.) of
voor categorieen die staatsrechtelijk naast ministeries staan (Hoge Colleges
van Staat, Rechtspraak, Openbaar Ministerie).

Idempotent: opnieuw draaien doet niets als de groepen al bestaan.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid


@dataclass(frozen=True)
class SynthetischeGroep:
    naam: str
    type: str
    afkorting: str | None
    beschrijving: str


GROEPEN: tuple[SynthetischeGroep, ...] = (
    SynthetischeGroep(
        naam="Hoge Colleges van Staat",
        type="synthetische_groep",
        afkorting="HCvS",
        beschrijving=(
            "Grondwettelijke instellingen die naast de regering staan: "
            "Raad van State, Algemene Rekenkamer, Nationale Ombudsman, "
            "Eerste en Tweede Kamer, Kabinet van de Koning, Kiesraad."
        ),
    ),
    SynthetischeGroep(
        naam="Rechtspraak",
        type="synthetische_groep",
        afkorting=None,
        beschrijving=(
            "Onafhankelijke rechtsprekende macht: Hoge Raad, Raad voor de "
            "Rechtspraak en alle gerechten."
        ),
    ),
    SynthetischeGroep(
        naam="Openbaar Ministerie",
        type="synthetische_groep",
        afkorting="OM",
        beschrijving="Het Openbaar Ministerie en arrondissementsparketten.",
    ),
    SynthetischeGroep(
        naam="Gemeenten",
        type="synthetische_groep",
        afkorting=None,
        beschrijving="Alle Nederlandse gemeenten.",
    ),
    SynthetischeGroep(
        naam="Provincies",
        type="synthetische_groep",
        afkorting=None,
        beschrijving="De twaalf provincies.",
    ),
    SynthetischeGroep(
        naam="Waterschappen",
        type="synthetische_groep",
        afkorting=None,
        beschrijving="Waterschappen en hoogheemraadschappen.",
    ),
    SynthetischeGroep(
        naam="Samenwerkingsorganisaties",
        type="synthetische_groep",
        afkorting=None,
        beschrijving=(
            "Gemeenschappelijke regelingen, omgevingsdiensten, "
            "veiligheidsregio's en andere samenwerkingsverbanden."
        ),
    ),
    SynthetischeGroep(
        naam="Caribische openbare lichamen",
        type="synthetische_groep",
        afkorting=None,
        beschrijving="Bonaire, Sint Eustatius en Saba (BES-eilanden).",
    ),
    SynthetischeGroep(
        naam="ZBO's en agentschappen",
        type="synthetische_groep",
        afkorting=None,
        beschrijving=(
            "Vangnet voor zelfstandige bestuursorganen en agentschappen "
            "die niet eenduidig onder een ministerie te plaatsen zijn."
        ),
    ),
    SynthetischeGroep(
        naam="Marktpartijen en overige",
        type="synthetische_groep",
        afkorting=None,
        beschrijving=(
            "Marktpartijen, stichtingen, koepelorganisaties en andere "
            "externe organisaties die geen overheidsorgaan zijn."
        ),
    ),
    SynthetischeGroep(
        naam="Internationale organisaties",
        type="synthetische_groep",
        afkorting=None,
        beschrijving=(
            "EU-instellingen, VN-organen, OECD, NAVO en andere "
            "internationale organen waar NL-stakeholders mee samenwerken."
        ),
    ),
    SynthetischeGroep(
        naam="Onderwijsinstellingen",
        type="synthetische_groep",
        afkorting=None,
        beschrijving=(
            "Universiteiten, hogescholen, mbo-instellingen. Niet in TOOI "
            "maar vaak gekoppeld aan beleidsdossiers."
        ),
    ),
)


async def seed(session: AsyncSession) -> None:
    """Maak ontbrekende synthetische groepen aan."""
    bestaand = (
        (
            await session.execute(
                select(OrganisatieEenheid.naam).where(
                    OrganisatieEenheid.bron == "synthetisch"
                )
            )
        )
        .scalars()
        .all()
    )
    bestaande_namen = set(bestaand)

    nieuwe = 0
    for groep in GROEPEN:
        if groep.naam in bestaande_namen:
            continue
        session.add(
            OrganisatieEenheid(
                naam=groep.naam,
                type=groep.type,
                afkorting=groep.afkorting,
                beschrijving=groep.beschrijving,
                bron="synthetisch",
            )
        )
        nieuwe += 1
    await session.commit()
    print(
        f"Seed synthetische groepen: {nieuwe} aangemaakt, {len(GROEPEN) - nieuwe} bestonden al"  # noqa: E501
    )


async def main() -> None:
    async with async_session() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
