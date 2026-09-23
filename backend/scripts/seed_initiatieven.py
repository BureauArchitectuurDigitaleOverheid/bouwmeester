"""Mock data for initiatieven, so the initiatief page has something to show.

Each tab of the initiatief page needs content to be judged locally: leads in
every funnel column (some with an overdue next action), members with each
role, linked eenheden, stakeholders, parliamentary search terms with hits, a
Mattermost channel, and updates both published and in draft. The four
initiatieven are deliberately uneven, because an overview where every card
looks the same says nothing about how it reads when one is busy and another
is empty:

- Regelrecht: full, funnel scores on, public page on.
- Fundament: moderately filled.
- Appmanager: two leads and nothing else.
- Nerds: no leads at all.

All names of organisations and people here are fictional or generic; persons
come from whatever the main seed put in the database.

Run on its own against an existing database with `just seed-initiatieven`.
It is idempotent: an initiatief that already has leads is left alone.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.core.slug import slugify
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.repositories.lead_column import LeadColumnRepository

# (naam, kleur, beschrijving). kleur is an nldd-tag color name from
# schema.initiatief.INITIATIEF_COLORS, never a hex.
INITIATIEVEN = [
    (
        "Regelrecht",
        "lintblauw",
        "Wetgeving als uitvoerbare code, met en voor uitvoerders.",
    ),
    ("Fundament", "groen", "Gedeelde bouwstenen voor digitale overheidsdiensten."),
    ("Appmanager", "oranje", "Beheer van overheidsapps in de stores."),
    ("Nerds", "paars", "Nederlandse Richtlijn Digitale Systemen."),
]

# (title, organization, stage, days until next action or None, engagement_type,
#  scores (strategisch, politiek, positie) or None, public)
_Lead = tuple[str, str, str, int | None, str | None, tuple[int, int, int] | None, bool]

LEADS: dict[str, list[_Lead]] = {
    "Regelrecht": [
        (
            "Zorgtoeslag als referentiecasus",
            "Uitvoeringsorganisatie Toeslagen",
            "follow_up",
            -4,
            "intern_oppakken",
            (5, 4, 5),
            True,
        ),
        (
            "Gemeentelijke bijzondere bijstand",
            "Gemeente Voorbeeldstad",
            "eerste_gesprek",
            2,
            "verkenning",
            (4, 3, 3),
            True,
        ),
        (
            "Kinderopvangtoeslag doorrekenen",
            "Ministerie van SZW, directie Kinderopvang",
            "interne_check",
            -1,
            "voorbereiden_eigen_team",
            (4, 5, 4),
            True,
        ),
        (
            "Huurtoeslag scenario's",
            "Woningcorporatie De Voorbeeldhoek",
            "verkennen",
            7,
            "verkenning",
            (3, 2, 2),
            False,
        ),
        (
            "Wetgevingsjuristen trainen",
            "Academie voor Wetgeving",
            "verkennen",
            14,
            "betrokken_houden",
            (3, 3, 4),
            False,
        ),
        (
            "Studiefinanciering uitvoeringstoets",
            "Uitvoeringsorganisatie Onderwijs",
            "in_the_pocket",
            None,
            "intern_oppakken",
            (5, 4, 4),
            True,
        ),
        (
            "Europese samenwerking rules-as-code",
            "Europees netwerk digitale overheid",
            "koelkast",
            None,
            "nog_te_bepalen",
            (2, 2, 3),
            False,
        ),
        (
            "Vraag van een provincie over subsidieregels",
            "Provincie Voorbeeldland",
            "inbox",
            None,
            None,
            None,
            False,
        ),
        (
            "Inkomensafhankelijke regelingen bundelen",
            "Planbureau (fictief)",
            "inbox",
            1,
            None,
            None,
            False,
        ),
    ],
    "Fundament": [
        (
            "Gedeelde inlogvoorziening",
            "Uitvoeringsorganisatie Identiteit",
            "eerste_gesprek",
            3,
            None,
            None,
            False,
        ),
        (
            "API-register vullen",
            "Stichting Open Standaarden (fictief)",
            "verkennen",
            -2,
            None,
            None,
            False,
        ),
        (
            "Notificatiedienst hergebruiken",
            "Gemeente Voorbeeldstad",
            "follow_up",
            5,
            None,
            None,
            False,
        ),
        (
            "Designsystem adopteren",
            "Waterschap De Voorbeeldpolder",
            "in_the_pocket",
            None,
            None,
            None,
            False,
        ),
        (
            "Berichtenbox koppelen",
            "Uitvoeringsorganisatie Belastingen",
            "koelkast",
            None,
            None,
            None,
            False,
        ),
    ],
    "Appmanager": [
        (
            "App van een inspectie overnemen",
            "Inspectiedienst (fictief)",
            "verkennen",
            10,
            None,
            None,
            False,
        ),
        (
            "Store-accounts consolideren",
            "Ministerie (fictief), directie Communicatie",
            "inbox",
            None,
            None,
            None,
            False,
        ),
    ],
    "Nerds": [],
}

# (titel, body, days ago published or None for a draft)
UPDATES: dict[str, list[tuple[str, str, int | None]]] = {
    "Regelrecht": [
        (
            "Zorgtoeslag rekent mee met de Belastingdienst",
            "De referentiecasus draait nu end-to-end, inclusief de toetsingsinkomens.",
            21,
        ),
        (
            "Eerste gemeente sluit aan",
            "Een gemeente test de bijzondere bijstand op de engine.",
            9,
        ),
        ("Schema 0.7 vrijgegeven", "Markeringen vervangen de onvertaalbaren.", 2),
        ("Concept: plannen voor het najaar", "Nog niet delen.", None),
    ],
    "Fundament": [
        ("Bouwstenen-overzicht online", "Alle gedeelde voorzieningen op één plek.", 30),
    ],
}

# (term, is_frase, treffers, weggeklikt, actief)
SEARCH_TERMS: dict[str, list[tuple[str, bool, int, int, bool]]] = {
    "Regelrecht": [
        ("Regelrecht", False, 4, 0, True),
        ("rules as code", True, 7, 2, True),
        ("uitvoerbare wetgeving", True, 2, 0, True),
        ("wetsanalyse", False, 12, 9, True),
        ("machineleesbare regels", True, 0, 0, False),
    ],
    "Fundament": [
        ("Generieke Digitale Infrastructuur", True, 15, 3, True),
        ("GDI", False, 31, 20, True),
    ],
}

# (belang 1-5, houding, invloed 1-5, notitie)
STAKEHOLDERS: dict[str, list[tuple[int, str, int, str]]] = {
    "Regelrecht": [
        (5, "voorstander", 4, "Trekker aan uitvoeringskant."),
        (4, "welwillend", 5, "Wil eerst resultaten zien."),
        (3, "kritisch", 3, "Zorgen over juridische verantwoording."),
        (2, "neutraal", 2, ""),
    ],
    "Fundament": [
        (4, "welwillend", 3, ""),
    ],
}

# (rol) per member slot after the owner
MEMBER_ROLES: dict[str, list[str]] = {
    "Regelrecht": ["contributor", "contributor", "contributor", "viewer"],
    "Fundament": ["contributor"],
    "Appmanager": [],
    "Nerds": ["contributor"],
}

EENHEID_COUNT: dict[str, int] = {"Regelrecht": 2, "Fundament": 1}


async def _get_or_create_initiatief(
    db: AsyncSession, naam: str, kleur: str, beschrijving: str
) -> Initiatief:
    existing = (
        await db.execute(select(Initiatief).where(Initiatief.naam == naam))
    ).scalar_one_or_none()
    if existing:
        return existing
    regelrecht = naam == "Regelrecht"
    init = Initiatief(
        naam=naam,
        slug=slugify(naam) or None,
        kleur=kleur,
        beschrijving=beschrijving,
        funnel_enabled=regelrecht,
        public_page_enabled=regelrecht,
        score_strategisch_label="Strategisch belang RR-kernteam"
        if regelrecht
        else None,
        score_politiek_label="Politiek-bestuurlijk belang" if regelrecht else None,
        score_positie_label="Belang voor positie/omgevingsmgt RR"
        if regelrecht
        else None,
    )
    db.add(init)
    await db.flush()
    # The script bypasses InitiatiefRepository.create, so the default funnel
    # columns are not seeded automatically.
    await LeadColumnRepository(db).seed_defaults(init.id)
    return init


async def _has_leads(db: AsyncSession, initiatief_id: UUID) -> bool:
    count = await db.scalar(
        select(func.count(Lead.id)).where(Lead.initiatief_id == initiatief_id)
    )
    return bool(count)


async def seed_initiatieven(db: AsyncSession, owner: Person | None = None) -> None:
    people = list(
        (
            await db.execute(
                select(Person)
                .where(Person.is_agent.is_(False), Person.is_active.is_(True))
                .order_by(Person.created_at)
                .limit(20)
            )
        ).scalars()
    )
    if owner is None and people:
        owner = people[0]
    others = [p for p in people if owner is None or p.id != owner.id]
    eenheden = list(
        (
            await db.execute(
                select(OrganisatieEenheid).order_by(OrganisatieEenheid.naam).limit(5)
            )
        ).scalars()
    )
    today = date.today()
    now = datetime.now(UTC)
    created = 0

    for index, (naam, kleur, beschrijving) in enumerate(INITIATIEVEN):
        init = await _get_or_create_initiatief(db, naam, kleur, beschrijving)
        if await _has_leads(db, init.id):
            print(f"  {naam}: heeft al leads, overgeslagen")
            continue
        created += 1

        # Members: the owner, then a rotating slice of the other people so
        # the initiatieven do not all share one team.
        member_ids: set[UUID] = set()
        if owner:
            db.add(
                ResourcePermission(
                    person_id=owner.id,
                    resource_type="initiatief",
                    resource_id=init.id,
                    rol="eigenaar",
                )
            )
            member_ids.add(owner.id)
        roles = MEMBER_ROLES.get(naam, [])
        for slot, rol in enumerate(roles):
            if not others:
                break
            person = others[(index * 3 + slot) % len(others)]
            if person.id in member_ids:
                continue
            member_ids.add(person.id)
            db.add(
                ResourcePermission(
                    person_id=person.id,
                    resource_type="initiatief",
                    resource_id=init.id,
                    rol=rol,
                )
            )
        for slot in range(min(EENHEID_COUNT.get(naam, 0), len(eenheden))):
            db.add(
                ResourcePermission(
                    organisatie_eenheid_id=eenheden[(index + slot) % len(eenheden)].id,
                    resource_type="initiatief",
                    resource_id=init.id,
                    rol="contributor" if slot == 0 else "viewer",
                )
            )

        member_list = [p for p in people if p.id in member_ids]
        for position, (title, org, stage, due, engagement, scores, public) in enumerate(
            LEADS.get(naam, [])
        ):
            lead = Lead(
                title=title,
                organization=org,
                description=f"{title}. Aangedragen via het netwerk van {naam}.",
                stage=stage,
                initiatief_id=init.id,
                sort_order=position,
                assignee_id=member_list[position % len(member_list)].id
                if member_list
                else None,
                next_action="Terugbellen over vervolgafspraak"
                if due is not None
                else None,
                next_action_date=today + timedelta(days=due)
                if due is not None
                else None,
                engagement_type=engagement,
                score_strategisch=scores[0] if scores else None,
                score_politiek=scores[1] if scores else None,
                score_positie=scores[2] if scores else None,
                public_visible=public,
                public_title=title if public else None,
                public_summary=f"We verkennen samen met {org} wat hier mogelijk is."
                if public
                else None,
            )
            db.add(lead)
            await db.flush()
            db.add(
                LeadActivity(
                    lead_id=lead.id,
                    author_id=lead.assignee_id,
                    content="Eerste contact gelegd.",
                    activity_type="note",
                )
            )

        for titel, body, days_ago in UPDATES.get(naam, []):
            published = now - timedelta(days=days_ago) if days_ago is not None else None
            db.add(
                InitiatiefUpdatePost(
                    initiatief_id=init.id,
                    titel=titel,
                    body=body,
                    published_at=published,
                    published_by_id=owner.id if owner and published else None,
                )
            )

        for term, is_frase, treffers, weggeklikt, actief in SEARCH_TERMS.get(naam, []):
            db.add(
                ParlementairAbonnement(
                    scope_type="initiatief",
                    scope_id=init.id,
                    term=term,
                    term_genormaliseerd=ParlementairAbonnement.normaliseer(term),
                    is_frase=is_frase,
                    actief=actief,
                    treffers_totaal=treffers,
                    weggeklikt_totaal=weggeklikt,
                    laatste_treffer_op=now - timedelta(days=treffers % 9)
                    if treffers
                    else None,
                    created_by_id=owner.id if owner else None,
                )
            )

        assessed = [p for p in people if p.id not in member_ids]
        for slot, (belang, houding, invloed, notitie) in enumerate(
            STAKEHOLDERS.get(naam, [])
        ):
            if slot >= len(assessed):
                break
            db.add(
                StakeholderAssessment(
                    person_id=assessed[-(slot + 1)].id,
                    scope_type="initiatief",
                    scope_id=init.id,
                    belang=belang,
                    houding=houding,
                    invloed=invloed,
                    notitie=notitie or None,
                    assessed_by_id=owner.id if owner else None,
                    assessed_at=now,
                )
            )

        if naam == "Regelrecht":
            # A fake channel id: Mattermost is off locally, so nothing ever
            # resolves it. It makes the Signalen tab show a linked channel.
            db.add(
                MattermostChannelLink(
                    channel_id="mockchannelregelrecht00000",
                    channel_name="regelrecht-signalen",
                    channel_display_name="Regelrecht signalen",
                    scope_type="initiatief",
                    scope_id=init.id,
                    suggest_leads_enabled=True,
                    parlementaire_alerts_enabled=True,
                    created_by_id=owner.id if owner else None,
                )
            )

    await db.flush()
    print(f"  Initiatieven: {created} gevuld met mockdata")


async def main() -> None:
    async with async_session() as db:
        await seed_initiatieven(db)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
