"""Seed script: realistic BZK/DGDOO Digitale Overheid dataset.

Run with: cd backend && uv run python scripts/seed.py
Clears all existing data and populates organisatie, personen, corpus, edges, and tasks.
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.repositories.corpus_node import CorpusNodeRepository
from bouwmeester.repositories.edge import EdgeRepository
from bouwmeester.repositories.edge_type import EdgeTypeRepository
from bouwmeester.repositories.organisatie_eenheid import OrganisatieEenheidRepository
from bouwmeester.repositories.person import PersonRepository
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.corpus_node import CorpusNodeCreate, CorpusNodeUpdate
from bouwmeester.schema.edge import EdgeCreate
from bouwmeester.schema.edge_type import EdgeTypeCreate
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
    OrganisatieEenheidUpdate,
)
from bouwmeester.schema.person import PersonCreate
from bouwmeester.schema.tag import TagCreate
from bouwmeester.schema.task import TaskCreate


def _generate_fallback_persons() -> dict:
    """Generate obviously fake placeholder persons when seed_persons.json is missing.

    This allows `just reset-db` to work without decryption keys (CI, new devs).
    """
    # Map of org_keys used by named persons
    org_keys_named = [
        "bzk",
        "dgdoo",
        "dir_ddo",
        "dir_ds",
        "dir_cio",
        "dir_ao",
        "dir_ifhr",
        "prog_open",
        "afd_basisinfra",
        "afd_id_toegang",
        "afd_wdo",
        "afd_dienstverlening",
        "bureau_arch",
        "afd_ds_a",
        "afd_ds_b",
        "afd_ds_c",
        "afd_ds_d",
        "afd_ict_voorz",
        "afd_istelsel",
        "afd_infobev",
        "afd_ambt_vak",
        "afd_arbeidsmarkt",
        "afd_inkoop",
        "afd_fac_huisv",
    ]
    functies_named = [
        "staatssecretaris",
        "directeur_generaal",
        "directeur",
        "directeur",
        "directeur",
        "directeur",
        "directeur",
        "directeur",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "coordinator",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
        "afdelingshoofd",
    ]
    keys_named = [
        "p_staatssec",
        "p_dgdoo",
        "p_dir_ddo",
        "p_dir_ds",
        "p_dir_cio",
        "p_dir_ao",
        "p_dir_ifhr",
        "p_dir_open",
        "p_ah_infra",
        "p_ah_id",
        "p_ah_wdo",
        "p_ah_dienst",
        "p_coord_arch",
        "p_ah_ds_a",
        "p_ah_ds_b",
        "p_ah_ds_c",
        "p_ah_ds_d",
        "p_ah_ict",
        "p_brouwer",
        "p_timmermans",
        "p_ah_ambt",
        "p_meijer",
        "p_ah_inkoop",
        "p_ah_fac",
    ]
    named_persons = []
    for i, key in enumerate(keys_named):
        named_persons.append(
            {
                "key": key,
                "naam": f"Persoon {key.removeprefix('p_').title()}",
                "email": f"{key.removeprefix('p_')}@placeholder.example",
                "functie": functies_named[i],
                "org_key": org_keys_named[i],
            }
        )

    tl_keys = [
        ("p_tl_digid", "team_digid"),
        ("p_tl_eudiw", "team_eudiw"),
        ("p_tl_mijnov", "team_mijnoverheid"),
        ("p_tl_gdi", "team_gdi"),
        ("p_tl_algo", "team_algo"),
        ("p_tl_aiact", "team_ai_act"),
        ("p_tl_data", "team_data"),
        ("p_tl_incl", "team_inclusie"),
        ("p_tl_eu", "team_eu_intl"),
        ("p_tl_comm", "team_comm"),
        ("p_tl_cloud", "team_cloud"),
        ("p_tl_sourc", "team_sourcing"),
        ("p_tl_arch", "team_arch"),
        ("p_tl_ciostel", "team_cio_stelsel"),
        ("p_tl_bio", "team_bio"),
        ("p_tl_cao", "team_cao"),
        ("p_tl_div", "team_diversiteit"),
        ("p_tl_woo", "team_woo"),
        ("p_tl_actie", "team_actieplan"),
    ]
    team_leaders = [
        {
            "key": k,
            "naam": f"Teamleider {k.removeprefix('p_tl_').title()}",
            "functie": "coordinator",
            "org_key": org,
        }
        for k, org in tl_keys
    ]

    # Minimal bulk people — just enough to satisfy the named_bulk_refs
    bulk_names = {
        "Persoon Kaya": ("senior_beleidsmedewerker", "afd_id_toegang", "p_kaya"),
        "Persoon Nguyen": ("beleidsmedewerker", "team_digid", "p_nguyen"),
        "Persoon Visser": ("projectleider", "team_mijnoverheid", "p_visser"),
        "Persoon DeJong": ("senior_beleidsmedewerker", "team_ai_act", "p_dejong"),
        "Persoon Kumar": ("senior_beleidsmedewerker", "team_data", "p_kumar"),
        "Persoon Hendriks": ("beleidsmedewerker", "team_inclusie", "p_hendriks"),
        "Persoon DeVries": ("senior_beleidsmedewerker", "team_cloud", "p_devries"),
        "Persoon VanDenBerg": ("senior_beleidsmedewerker", "team_bio", "p_berg"),
        "Persoon Peeters": (
            "senior_beleidsmedewerker",
            "afd_arbeidsmarkt",
            "p_peeters",
        ),
        "Persoon Achterberg": ("jurist", "afd_wdo", "p_achterberg"),
    }
    bulk_people = [
        {
            "naam": naam,
            "email_prefix": naam.lower().replace(" ", "."),
            "functie": functie,
            "org_key": org,
        }
        for naam, (functie, org, _) in bulk_names.items()
    ]
    named_bulk_refs = {naam: ref for naam, (_, _, ref) in bulk_names.items()}

    return {
        "named_persons": named_persons,
        "team_leaders": team_leaders,
        "bulk_people": bulk_people,
        "named_bulk_refs": named_bulk_refs,
        "team_leader_aliases": {
            "p_tl_algo": "p_bakker",
            "p_tl_arch": "p_smit",
            "p_tl_sourc": "p_jansen",
        },
    }


async def seed(db: AsyncSession) -> None:
    # Clear existing data (order matters due to FKs)
    for table in [
        "notification",
        "mention",
        "suggested_edge",
        "parlementair_item",
        "node_tag",
        "tag",
        "task",
        "node_stakeholder",
        "edge",
        "edge_type",
        "probleem",
        "effect",
        "beleidsoptie",
        "dossier",
        "doel",
        "instrument",
        "beleidskader",
        "maatregel",
        "politieke_input",
        "corpus_node_title",
        "corpus_node_status",
        "corpus_node",
        "person_organisatie_eenheid",
        "organisatie_eenheid_manager",
        "organisatie_eenheid_parent",
        "organisatie_eenheid_naam",
        "person",
        "organisatie_eenheid",
    ]:
        await db.execute(text(f"DELETE FROM {table}"))
    await db.flush()

    org_repo = OrganisatieEenheidRepository(db)
    person_repo = PersonRepository(db)
    node_repo = CorpusNodeRepository(db)
    edge_type_repo = EdgeTypeRepository(db)
    edge_repo = EdgeRepository(db)
    task_repo = TaskRepository(db)
    tag_repo = TagRepository(db)

    # =========================================================================
    # 1. ORGANISATIE — BZK / DGDOO (realistic ~200 FTE structure)
    # =========================================================================

    bzk = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
            type="ministerie",
            beschrijving=(
                "Verantwoordelijk voor de democratische rechtstaat, digitalisering, "
                "openbaar bestuur, wonen en de AIVD."
            ),
        )
    )

    dgdoo = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="DG Digitalisering en Overheidsorganisatie",
            type="directoraat_generaal",
            parent_id=bzk.id,
            beschrijving=(
                "Directoraat-Generaal verantwoordelijk voor digitalisering van de "
                "overheid, digitale samenleving, CIO Rijk en overheidsorganisatie. "
                "Circa 250 medewerkers."
            ),
        )
    )

    # --- Directie Digitale Overheid (~50 FTE) ---
    dir_ddo = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Digitale Overheid",
            type="directie",
            parent_id=dgdoo.id,
            beschrijving=(
                "Beleid en wetgeving voor digitale overheidsdienstverlening, inclusief "
                "Wet Digitale Overheid, DigiD, MijnOverheid en digitale identiteit."
            ),
        )
    )

    afd_basisinfra = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Basisinfrastructuur",
            type="afdeling",
            parent_id=dir_ddo.id,
            beschrijving=("GDI, standaarden, architectuur en basisregistraties."),
        )
    )
    afd_id_toegang = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Identiteit en BRP",
            type="afdeling",
            parent_id=dir_ddo.id,
            beschrijving=(
                "DigiD, eIDAS, Europese digitale identiteit (EUDIW), BRP en "
                "inlogmiddelen."
            ),
        )
    )
    afd_wdo = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Data en Toegang",
            type="afdeling",
            parent_id=dir_ddo.id,
            beschrijving=(
                "Data, toegang, Wet Digitale Overheid en digitale identiteit."
            ),
        )
    )
    afd_dienstverlening = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Dienstverlening",
            type="afdeling",
            parent_id=dir_ddo.id,
            beschrijving=(
                "MijnOverheid, machtigen en digitale overheidsdienstverlening."
            ),
        )
    )

    # --- Bureau Architectuur (under Basisinfrastructuur) ---
    bureau_arch = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Architectuur",
            type="bureau",
            parent_id=afd_basisinfra.id,
            beschrijving=(
                "Architectuur en ontwerp voor digitale overheidsdienstverlening."
            ),
        )
    )
    team_standaarden = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Standaardisatie en Interoperabiliteit",
            type="team",
            parent_id=bureau_arch.id,
            beschrijving="Standaarden en interoperabiliteit.",
        )
    )
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Architectuur",
            type="team",
            parent_id=bureau_arch.id,
            beschrijving="Enterprise-architectuur, NORA en referentie-architecturen.",
        )
    )
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Strategie",
            type="team",
            parent_id=bureau_arch.id,
            beschrijving="Strategisch advies digitale overheid.",
        )
    )

    # --- Bureau MIDO (under Basisinfrastructuur) ---
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="MIDO",
            type="bureau",
            parent_id=afd_basisinfra.id,
            beschrijving=("Meerjarige Investeringsplanning Digitale Overheid."),
        )
    )

    # --- Cluster MijnOverheid (under Basisinfrastructuur) ---
    cluster_mijnoverheid = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="MijnOverheid",
            type="cluster",
            parent_id=afd_basisinfra.id,
            beschrijving="Doorontwikkeling en beheer van het MijnOverheid-portaal.",
        )
    )

    # --- Clusters under Data en Toegang ---
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Data",
            type="cluster",
            parent_id=afd_wdo.id,
            beschrijving="Databeleid en datastrategie.",
        )
    )
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Toegang",
            type="cluster",
            parent_id=afd_wdo.id,
            beschrijving="Toegangsbeleid en authenticatie.",
        )
    )
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="WDO",
            type="cluster",
            parent_id=afd_wdo.id,
            beschrijving="Wet Digitale Overheid en stelselwetgeving.",
        )
    )
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Digitale Identiteit",
            type="cluster",
            parent_id=afd_wdo.id,
            beschrijving=(
                "Europese Digitale Identiteit Wallet en digitale identiteit."
            ),
        )
    )

    # --- Teams under Identiteit en BRP ---
    team_digid = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="DigiD Beleid",
            type="team",
            parent_id=afd_id_toegang.id,
            beschrijving="Beleidsregie op DigiD als publieke authenticatievoorziening.",
        )
    )
    team_eudiw = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="EUDIW",
            type="team",
            parent_id=afd_id_toegang.id,
            beschrijving=(
                "Europese Digitale Identiteit Wallet — Nederlandse implementatie en "
                "pilotprogramma."
            ),
        )
    )

    # Backward-compat aliases for downstream references
    team_mijnoverheid = cluster_mijnoverheid
    team_gdi = team_standaarden

    # --- Directie Digitale Samenleving (~50 FTE) ---
    dir_ds = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Digitale Samenleving",
            type="directie",
            parent_id=dgdoo.id,
            beschrijving=(
                "Beleid voor algoritmes, AI, data-ethiek, online veiligheid, digitale "
                "inclusie en de verhouding burger-technologie."
            ),
        )
    )

    afd_ds_a = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Bedrijfsvoering en Control",
            type="afdeling",
            parent_id=dir_ds.id,
            beschrijving=(
                "Bedrijfsvoering, portfoliomanagement, financiën & control, "
                "secretariaat."
            ),
        )
    )
    afd_ds_b = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Strategie en Internationaal",
            type="afdeling",
            parent_id=dir_ds.id,
            beschrijving=(
                "Communicatie en communitymanagement, internationaal, strategie en "
                "coördinatie, Caribisch Nederland, Werkagenda."
            ),
        )
    )
    afd_ds_c = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Publieke Waarden en Veiligheid",
            type="afdeling",
            parent_id=dir_ds.id,
            beschrijving=(
                "Informatieveiligheid, publieke waarden en nieuwe technologie "
                "(kinderrechten online, desinformatie, digitale gemeenschapsgoederen)."
            ),
        )
    )
    afd_ds_d = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Data, AI en Inclusie",
            type="afdeling",
            parent_id=dir_ds.id,
            beschrijving=("Data, AI en algoritmen, digitale inclusie."),
        )
    )

    # Backward-compat aliases for downstream references
    afd_ai_data = afd_ds_d
    afd_strat_intl = afd_ds_b
    team_algo = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Algoritmeregister",
            type="team",
            parent_id=afd_ai_data.id,
            beschrijving=(
                "Beheer en doorontwikkeling van het overheidsbreed Algoritmeregister."
            ),
        )
    )
    team_ai_act = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="AI Act Implementatie",
            type="team",
            parent_id=afd_ai_data.id,
            beschrijving=(
                "Implementatie EU AI-verordening, algoritmekader en toezichtsketen."
            ),
        )
    )
    team_data = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Data en IBDS",
            type="team",
            parent_id=afd_ai_data.id,
            beschrijving=(
                "Interbestuurlijke Datastrategie, Federatief Datastelsel en open data."
            ),
        )
    )
    team_inclusie = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Digitale Inclusie",
            type="team",
            parent_id=afd_ai_data.id,
            beschrijving=(
                "Digitale geletterdheid, toegankelijkheid en het"
                " voorkomen van digitale uitsluiting."
            ),
        )
    )
    team_eu_intl = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="EU en Internationaal",
            type="team",
            parent_id=afd_strat_intl.id,
            beschrijving=(
                "EU-raden TTE Telecom, OECD digitaal beleid, bilaterale samenwerking."
            ),
        )
    )
    team_comm = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Communicatie en Strategie",
            type="team",
            parent_id=afd_strat_intl.id,
            beschrijving=(
                "NDS-communicatie, stakeholdermanagement en strategische advisering."
            ),
        )
    )

    # --- Directie CIO Rijk (~45 FTE) ---
    dir_cio = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="CIO Rijk",
            type="directie",
            parent_id=dgdoo.id,
            beschrijving=(
                "Rijksbrede ICT-governance, CIO-stelsel, cloud- en "
                "IT-architectuurbeleid, I-strategie Rijksdienst."
            ),
        )
    )

    afd_ict_voorz = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="ICT-diensten en Voorzieningen",
            type="afdeling",
            parent_id=dir_cio.id,
            beschrijving=(
                "Cloudbeleid Rijk, soevereiniteit,"
                " datacentersstrategie, CTO-stelsel en technische standaarden."
            ),
        )
    )
    afd_istelsel = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="I-Stelsel en Vakmanschap",
            type="afdeling",
            parent_id=dir_cio.id,
            beschrijving=(
                "CIO-stelsel, enterprise-architectuur Rijk, NORA, digitaal vakmanschap."
            ),
        )
    )
    afd_infobev = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Informatiebeveiliging",
            type="afdeling",
            parent_id=dir_cio.id,
            beschrijving=(
                "BIO-compliance, CISO Rijk, cyberveiligheid rijksoverheid en awareness."
            ),
        )
    )
    team_cloud = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Cloud en Soevereiniteit",
            type="team",
            parent_id=afd_ict_voorz.id,
            beschrijving=(
                "Cloudbeleid, soevereine cloud, exit-strategieën en marktordening."
            ),
        )
    )
    team_sourcing = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Sourcing en Leveranciersmanagement",
            type="team",
            parent_id=afd_ict_voorz.id,
            beschrijving=(
                "Regie op IT-leveranciers, marktordening en vendor lock-in preventie."
            ),
        )
    )
    team_arch = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Architectuur en NORA",
            type="team",
            parent_id=afd_istelsel.id,
            beschrijving=(
                "Enterprise-architectuur Rijk, NORA-beheer en referentie-architecturen."
            ),
        )
    )
    team_cio_stelsel = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="CIO-stelsel",
            type="team",
            parent_id=afd_istelsel.id,
            beschrijving=(
                "CIO-overleg, nieuwe rollen CDO/CPO/CTO, governance-herziening."
            ),
        )
    )
    team_bio = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="BIO en Cyberveiligheid",
            type="team",
            parent_id=afd_infobev.id,
            beschrijving=(
                "Baseline Informatiebeveiliging Overheid, audits en awareness."
            ),
        )
    )

    # --- Directie Ambtenaar & Organisatie (~30 FTE) ---
    dir_ao = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Ambtenaar en Organisatie",
            type="directie",
            parent_id=dgdoo.id,
            beschrijving=(
                "Arbeidsvoorwaarden rijkspersoneel, HR-beleid, organisatieontwikkeling "
                "en diversiteitsbeleid."
            ),
        )
    )
    afd_ambt_vak = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Ambtelijk Vakmanschap en Rechtspositie",
            type="afdeling",
            parent_id=dir_ao.id,
            beschrijving=(
                "Ambtelijk vakmanschap, arbeidsvoorwaarden, rechtspositie en de "
                "Ambtenarenwet."
            ),
        )
    )
    afd_arbeidsmarkt = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Arbeidsmarkt en Organisatie",
            type="afdeling",
            parent_id=dir_ao.id,
            beschrijving=(
                "Werving, arbeidsmarktcommunicatie, diversiteit en "
                "organisatieontwikkeling Rijksdienst."
            ),
        )
    )
    team_cao = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="CAO en Arbeidsvoorwaarden",
            type="team",
            parent_id=afd_ambt_vak.id,
            beschrijving=(
                "CAO Rijk onderhandelingen, salarisbeleid en secundaire "
                "arbeidsvoorwaarden."
            ),
        )
    )
    team_diversiteit = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Diversiteit en Inclusie",
            type="team",
            parent_id=afd_arbeidsmarkt.id,
            beschrijving=(
                "Diversiteitsbeleid, banenafspraak en inclusief werkgeverschap "
                "Rijksdienst."
            ),
        )
    )

    # --- Directie IFHR (~30 FTE) ---
    dir_ifhr = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Inkoop-, Facilitair en Huisvestingsbeleid Rijk",
            type="directie",
            parent_id=dgdoo.id,
            beschrijving=(
                "Rijksbreed beleid voor inkoop en aanbesteding, facilitaire "
                "dienstverlening en huisvesting."
            ),
        )
    )
    afd_inkoop = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Inkoop- en Aanbestedingsbeleid Rijk",
            type="afdeling",
            parent_id=dir_ifhr.id,
            beschrijving=(
                "Inkoopbeleid, aanbestedingsrecht, categoriemanagement en "
                "maatschappelijk verantwoord inkopen."
            ),
        )
    )
    afd_fac_huisv = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Faciliteiten- en Huisvestingsbeleid",
            type="afdeling",
            parent_id=dir_ifhr.id,
            beschrijving=(
                "Rijkshuisvesting, facilitaire dienstverlening, hybride werken en "
                "verduurzaming kantoren."
            ),
        )
    )

    # --- Programma Open Overheid (~15 FTE) ---
    prog_open = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Programma Open Overheid",
            type="directie",
            parent_id=dgdoo.id,
            beschrijving=(
                "Actieplan Open Overheid, Wet open overheid (Woo), "
                "informatiehuishouding en transparantie."
            ),
        )
    )
    team_woo = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Woo en Informatiehuishouding",
            type="team",
            parent_id=prog_open.id,
            beschrijving=(
                "Implementatie Wet open overheid, actieve openbaarmaking en "
                "informatiehuishouding."
            ),
        )
    )
    team_actieplan = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Actieplan Open Overheid",
            type="team",
            parent_id=prog_open.id,
            beschrijving=(
                "Nationaal Actieplan Open Overheid en Open Government Partnership."
            ),
        )
    )

    # --- De Digitale Dienst (under DGDOO) ---
    dienst_dd = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="De Digitale Dienst",
            type="dienst",
            parent_id=dgdoo.id,
            beschrijving=(
                "Uitvoeringsorganisatie voor digitale voorzieningen en dienstverlening."
            ),
        )
    )
    afd_zonder_mensen = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Zonder Mensen",
            type="afdeling",
            parent_id=dienst_dd.id,
            beschrijving="Geautomatiseerde processen en zelfbedieningsoplossingen.",
        )
    )

    # --- Bestuursstaf BZK ---
    staf_bzk = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Bestuursstaf BZK",
            type="directoraat_generaal",
            parent_id=bzk.id,
            beschrijving=(
                "SG, pSG, woordvoering, parlementaire zaken, juridische zaken."
            ),
        )
    )

    org_count = 43  # approximate
    print(f"  Organisatie: ~{org_count} eenheden aangemaakt")

    # =========================================================================
    # 2. PERSONEN (~200 medewerkers) — loaded from seed_persons.json
    # =========================================================================

    # Helper to create people in bulk
    def _email_from_name(naam: str) -> str:
        """Generate voornaam.achternaam@minbzk.nl from full name."""
        import unicodedata

        normalized = unicodedata.normalize("NFKD", naam)
        ascii_name = normalized.encode("ascii", "ignore").decode()
        parts = ascii_name.lower().split()
        voornaam = parts[0]
        rest = "".join(parts[1:])
        return f"{voornaam}.{rest}@minbzk.nl"

    async def cp(naam, email, functie, eenheid):
        if email is None:
            email = _email_from_name(naam)
        person = await person_repo.create(
            PersonCreate(
                naam=naam,
                email=email,
                functie=functie,
            )
        )
        # Create org placement
        placement = PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=eenheid.id,
            dienstverband="in_dienst",
            start_datum=date.today(),
        )
        db.add(placement)
        await db.flush()
        return person

    # Build org_map: string keys → org unit objects
    org_map = {
        "bzk": bzk,
        "dgdoo": dgdoo,
        "dir_ddo": dir_ddo,
        "dir_ds": dir_ds,
        "dir_cio": dir_cio,
        "dir_ao": dir_ao,
        "dir_ifhr": dir_ifhr,
        "prog_open": prog_open,
        "afd_basisinfra": afd_basisinfra,
        "afd_id_toegang": afd_id_toegang,
        "afd_wdo": afd_wdo,
        "afd_dienstverlening": afd_dienstverlening,
        "bureau_arch": bureau_arch,
        "afd_ds_a": afd_ds_a,
        "afd_ds_b": afd_ds_b,
        "afd_ds_c": afd_ds_c,
        "afd_ds_d": afd_ds_d,
        "afd_ict_voorz": afd_ict_voorz,
        "afd_istelsel": afd_istelsel,
        "afd_infobev": afd_infobev,
        "afd_ambt_vak": afd_ambt_vak,
        "afd_arbeidsmarkt": afd_arbeidsmarkt,
        "afd_inkoop": afd_inkoop,
        "afd_fac_huisv": afd_fac_huisv,
        "afd_ai_data": afd_ai_data,
        "afd_strat_intl": afd_strat_intl,
        "team_digid": team_digid,
        "team_eudiw": team_eudiw,
        "team_mijnoverheid": team_mijnoverheid,
        "team_gdi": team_gdi,
        "team_algo": team_algo,
        "team_ai_act": team_ai_act,
        "team_data": team_data,
        "team_inclusie": team_inclusie,
        "team_eu_intl": team_eu_intl,
        "team_comm": team_comm,
        "team_cloud": team_cloud,
        "team_sourcing": team_sourcing,
        "team_arch": team_arch,
        "team_cio_stelsel": team_cio_stelsel,
        "team_bio": team_bio,
        "team_cao": team_cao,
        "team_diversiteit": team_diversiteit,
        "team_woo": team_woo,
        "team_actieplan": team_actieplan,
        "staf_bzk": staf_bzk,
        "dienst_dd": dienst_dd,
        "afd_zonder_mensen": afd_zonder_mensen,
    }

    # Load person data from JSON (or decrypt from .age, or generate fallback)
    persons_json_path = Path(__file__).parent / "seed_persons.json"
    age_path = Path(__file__).parent / "seed_persons.json.age"
    if persons_json_path.exists():
        with open(persons_json_path) as f:
            persons_data = json.load(f)
        print("  Personen: laden uit seed_persons.json")
    elif os.environ.get("AGE_SECRET_KEY") and age_path.exists():
        from pyrage import decrypt as age_decrypt
        from pyrage import x25519

        identity = x25519.Identity.from_str(os.environ["AGE_SECRET_KEY"])
        decrypted = age_decrypt(age_path.read_bytes(), [identity])
        persons_data = json.loads(decrypted)
        print("  Personen: gedecrypt uit seed_persons.json.age (AGE_SECRET_KEY)")
    else:
        print(
            "  ⚠ seed_persons.json niet gevonden — gebruik placeholder-personen. "
            "Decrypt met: just decrypt-seed"
        )
        # Generate fake placeholder data with the same structure
        persons_data = _generate_fallback_persons()

    person_map: dict[str, object] = {}

    # Create named persons (bewindspersonen, directeuren, afdelingshoofden)
    for entry in persons_data["named_persons"]:
        p = await cp(
            entry["naam"],
            entry["email"],
            entry["functie"],
            org_map[entry["org_key"]],
        )
        person_map[entry["key"]] = p

    # Create team leaders
    for entry in persons_data["team_leaders"]:
        p = await cp(
            entry["naam"],
            None,
            entry["functie"],
            org_map[entry["org_key"]],
        )
        person_map[entry["key"]] = p

    # Create bulk people and track named references
    named_bulk_refs = persons_data.get("named_bulk_refs", {})
    for entry in persons_data["bulk_people"]:
        p = await cp(
            entry["naam"],
            None,
            entry["functie"],
            org_map[entry["org_key"]],
        )
        # If this person has a named reference, store it
        ref_key = named_bulk_refs.get(entry["naam"])
        if ref_key:
            person_map[ref_key] = p

    # Set up team leader aliases (e.g. p_bakker = p_tl_algo)
    for tl_key, alias_key in persons_data.get("team_leader_aliases", {}).items():
        person_map.setdefault(alias_key, person_map[tl_key])

    person_count = (
        len(persons_data["named_persons"])
        + len(persons_data["team_leaders"])
        + len(persons_data["bulk_people"])
    )
    print(f"  Personen: {person_count} personen aangemaakt")

    # Convenience accessor — returns None for missing keys (needed for
    # nullable bulk refs that may not exist in fallback mode)
    def pm(key: str):
        return person_map.get(key)

    # =========================================================================
    # 2a. AGENTS
    # =========================================================================

    async def create_agent(naam, description, eenheid):
        api_key = f"bm_{''.join(f'{b:02x}' for b in uuid.uuid4().bytes[:16])}"
        agent = await person_repo.create(
            PersonCreate(
                naam=naam,
                description=description,
                is_agent=True,
                api_key=api_key,
            )
        )
        placement = PersonOrganisatieEenheid(
            person_id=agent.id,
            organisatie_eenheid_id=eenheid.id,
            dienstverband="in_dienst",
            start_datum=date.today(),
        )
        db.add(placement)
        await db.flush()
        return agent

    # Domain-specialist agents in "Afdeling Zonder Mensen"
    # Named after characters from Bordewijk's novel "Karakter"
    agent_identiteit = await create_agent(
        "Dreverhaven",
        "Beleidsmedewerker digitale identiteit en authenticatie (eID, DigiD, eIDAS)",
        afd_zonder_mensen,
    )
    agent_open = await create_agent(
        "Katadreuffe",
        "Beleidsmedewerker transparantie, Woo-implementatie en actieve openbaarmaking",
        afd_zonder_mensen,
    )
    agent_algo = await create_agent(
        "Stroomkoning",
        "Adviseur algoritmeverantwoording, AI-verordening en publieke waarden",
        afd_zonder_mensen,
    )
    agent_interop = await create_agent(
        "De Gankelaar",
        (
            "Beleidsmedewerker standaarden, stelselafspraken en Europese "
            "interoperabiliteit"
        ),
        afd_zonder_mensen,
    )
    agent_infosec = await create_agent(
        "Rentenstein",
        "Beleidsmedewerker BIO-naleving, dreigingsanalyse en informatiebeveiliging",
        afd_zonder_mensen,
    )

    print("  Agents: 5 agents aangemaakt (Afdeling Zonder Mensen)")

    # =========================================================================
    # 2b. SET MANAGERS on organisatie-eenheden
    # =========================================================================

    manager_assignments = [
        (bzk, pm("p_staatssec")),
        (dgdoo, pm("p_dgdoo")),
        (dir_ddo, pm("p_dir_ddo")),
        (dir_ds, pm("p_dir_ds")),
        (dir_cio, pm("p_dir_cio")),
        (dir_ao, pm("p_dir_ao")),
        (dir_ifhr, pm("p_dir_ifhr")),
        (prog_open, pm("p_dir_open")),
        # Afdelingshoofden (ABD-benoemd)
        (afd_basisinfra, pm("p_ah_infra")),
        (afd_id_toegang, pm("p_ah_id")),
        (afd_wdo, pm("p_ah_wdo")),
        (afd_dienstverlening, pm("p_ah_dienst")),
        (bureau_arch, pm("p_coord_arch")),
        (afd_ds_a, pm("p_ah_ds_a")),
        (afd_ds_b, pm("p_ah_ds_b")),
        (afd_ds_c, pm("p_ah_ds_c")),
        (afd_ds_d, pm("p_ah_ds_d")),
        (afd_ict_voorz, pm("p_ah_ict")),
        (afd_istelsel, pm("p_brouwer")),
        (afd_infobev, pm("p_timmermans")),
        (afd_ambt_vak, pm("p_ah_ambt")),
        (afd_arbeidsmarkt, pm("p_meijer")),
        (afd_inkoop, pm("p_ah_inkoop")),
        (afd_fac_huisv, pm("p_ah_fac")),
        # Teamleiders
        (team_digid, pm("p_tl_digid")),
        (team_eudiw, pm("p_tl_eudiw")),
        (team_mijnoverheid, pm("p_tl_mijnov")),
        (team_gdi, pm("p_tl_gdi")),
        (team_algo, pm("p_tl_algo")),
        (team_ai_act, pm("p_tl_aiact")),
        (team_data, pm("p_tl_data")),
        (team_inclusie, pm("p_tl_incl")),
        (team_eu_intl, pm("p_tl_eu")),
        (team_comm, pm("p_tl_comm")),
        (team_cloud, pm("p_tl_cloud")),
        (team_sourcing, pm("p_tl_sourc")),
        (team_arch, pm("p_tl_arch")),
        (team_cio_stelsel, pm("p_tl_ciostel")),
        (team_bio, pm("p_tl_bio")),
        (team_cao, pm("p_tl_cao")),
        (team_diversiteit, pm("p_tl_div")),
        (team_woo, pm("p_tl_woo")),
        (team_actieplan, pm("p_tl_actie")),
        (afd_zonder_mensen, agent_identiteit),
    ]
    for unit, manager in manager_assignments:
        await org_repo.update(
            unit.id,
            OrganisatieEenheidUpdate(manager_id=manager.id),
        )

    print(f"  Managers: {len(manager_assignments)} managers toegewezen")

    # =========================================================================
    # 3. EDGE TYPES
    # =========================================================================

    edge_types = [
        EdgeTypeCreate(
            id="implementeert",
            label_nl="Implementeert",
            label_en="Implements",
            description="Het ene item implementeert of voert het andere uit.",
        ),
        EdgeTypeCreate(
            id="draagt_bij_aan",
            label_nl="Draagt bij aan",
            label_en="Contributes to",
            description="Het ene item draagt bij aan de realisatie van het andere.",
        ),
        EdgeTypeCreate(
            id="vloeit_voort_uit",
            label_nl="Vloeit voort uit",
            label_en="Derives from",
            description="Het ene item vloeit voort uit of is afgeleid van het andere.",
        ),
        EdgeTypeCreate(
            id="conflicteert_met",
            label_nl="Conflicteert met",
            label_en="Conflicts with",
            description="Spanningen of tegenstrijdigheden tussen twee items.",
        ),
        EdgeTypeCreate(
            id="verwijst_naar",
            label_nl="Verwijst naar",
            label_en="References",
            description="Het ene item verwijst expliciet naar het andere.",
        ),
        EdgeTypeCreate(
            id="vereist",
            label_nl="Vereist",
            label_en="Requires",
            description="Het ene item is een voorwaarde voor het andere.",
        ),
        EdgeTypeCreate(
            id="evalueert",
            label_nl="Evalueert",
            label_en="Evaluates",
            description="Het ene item beoordeelt of evalueert het andere.",
        ),
        EdgeTypeCreate(
            id="vervangt",
            label_nl="Vervangt",
            label_en="Replaces",
            description="Het ene item vervangt het andere.",
        ),
        EdgeTypeCreate(
            id="onderdeel_van",
            label_nl="Onderdeel van",
            label_en="Part of",
            description=(
                "Het ene item is een onderdeel of deelstrategie van het andere."
            ),
        ),
        EdgeTypeCreate(
            id="leidt_tot",
            label_nl="Leidt tot",
            label_en="Leads to",
            description=(
                "Causale relatie: het ene item leidt tot het andere (probleem→doel, "
                "maatregel→effect)."
            ),
        ),
        EdgeTypeCreate(
            id="adresseert",
            label_nl="Adresseert",
            label_en="Addresses",
            description=(
                "Het ene item adresseert of pakt het andere aan "
                "(maatregel/instrument→probleem)."
            ),
        ),
        EdgeTypeCreate(
            id="meet",
            label_nl="Meet",
            label_en="Measures",
            description=(
                "Het ene item meet of monitort het andere (effect→indicator/doel)."
            ),
        ),
    ]
    for et in edge_types:
        await edge_type_repo.create(et)

    print(f"  Edge types: {len(edge_types)} types aangemaakt")

    # =========================================================================
    # 4. CORPUS NODES
    # =========================================================================

    # --- Dossiers ---
    dos_digi_overheid = await node_repo.create(
        CorpusNodeCreate(
            title="Dossier Digitale Overheid",
            node_type="dossier",
            description=(
                "Koepeldossier voor alle beleidsontwikkeling rondom de digitale "
                "overheid: dienstverlening, identiteit, wetgeving en infrastructuur."
            ),
        )
    )
    dos_digi_samenleving = await node_repo.create(
        CorpusNodeCreate(
            title="Dossier Digitale Samenleving",
            node_type="dossier",
            description=(
                "Koepeldossier voor AI, algoritmen, data-ethiek, online veiligheid en "
                "digitale grondrechten."
            ),
        )
    )
    dos_cio_rijk = await node_repo.create(
        CorpusNodeCreate(
            title="Dossier CIO Rijk en ICT-Governance",
            node_type="dossier",
            description=(
                "Rijksbrede ICT-governance, CIO-stelsel, cloud, informatiebeveiliging "
                "en digitaal vakmanschap."
            ),
        )
    )
    dos_ai = await node_repo.create(
        CorpusNodeCreate(
            title="Dossier AI-regulering",
            node_type="dossier",
            description=(
                "Overheidsinzet van AI, algoritmetoezicht,"
                " AI-verordening implementatie en verantwoord gebruik."
            ),
            geldig_van=date(2023, 6, 1),
        )
    )
    dos_data = await node_repo.create(
        CorpusNodeCreate(
            title="Dossier Data en Interoperabiliteit",
            node_type="dossier",
            description=(
                "Datastrategie, Federatief Datastelsel, open data,"
                " basisregistraties en interoperabiliteit."
            ),
        )
    )

    # --- Beleidskaders ---
    bk_nds = await node_repo.create(
        CorpusNodeCreate(
            title="Nederlandse Digitaliseringsstrategie (NDS)",
            node_type="beleidskader",
            description=(
                "Eerste rijksbrede, interbestuurlijke digitaliseringsstrategie (juli "
                "2025). Zes prioriteiten: cloud, data, AI, dienstverlening, digitale "
                "weerbaarheid en digitaal vakmanschap. Benodigde investering: minimaal "
                "1 miljard euro per jaar tot 2030."
            ),
        )
    )
    bk_ibds = await node_repo.create(
        CorpusNodeCreate(
            title="Interbestuurlijke Datastrategie (IBDS)",
            node_type="beleidskader",
            description=(
                "Interbestuurlijke strategie voor verantwoord datagebruik. Kernbegrip: "
                "Federatief Datastelsel — data blijft lokaal beheerd maar wordt via "
                "afspraken beschikbaar gesteld. Eerste versie Afsprakenstelsel oktober "
                "2025."
            ),
        )
    )
    bk_wdo = await node_repo.create(
        CorpusNodeCreate(
            title="Wet Digitale Overheid (WDO)",
            node_type="beleidskader",
            status="concept",
            description=(
                "Wettelijk kader voor veilig inloggen bij de overheid en "
                "beveiligingsnormen. Gefaseerd van kracht sinds 1 juli 2023. "
                "Overgangstermijn verlengd tot 1 juli 2028."
                " DigiD Machtigen als publiek machtigingsstelsel."
            ),
            geldig_van=date(2021, 3, 1),
        )
    )
    bk_ai_act = await node_repo.create(
        CorpusNodeCreate(
            title="EU AI-verordening (AI Act) — Implementatie NL",
            node_type="beleidskader",
            description=(
                "Europese verordening voor AI-systemen."
                " Verboden AI sinds februari 2025 van kracht."
                " Hoog-risico AI-systemen moeten per augustus"
                " 2026 voldoen. Gemeenten moeten algoritmes"
                " publiceren. Nederland implementeert via"
                "het Algoritmekader."
            ),
        )
    )
    bk_cio_stelsel = await node_repo.create(
        CorpusNodeCreate(
            title="Besluit CIO-stelsel Rijksdienst 2026",
            node_type="beleidskader",
            description=(
                "Per 1 januari 2026 hernieuwd CIO-stelsel met bindende bevoegdheden "
                "voor CIO Rijk. Nieuwe rollen: CDO, CPO, CTO naast CIO en CISO. "
                "Escalatiebevoegdheid bij ontbrekende consensus. Staatscourant 2025, "
                "40208."
            ),
        )
    )
    bk_cloudbeleid = await node_repo.create(
        CorpusNodeCreate(
            title="Cloudbeleid Rijksoverheid (concept)",
            node_type="beleidskader",
            description=(
                "Kader voor verantwoord cloudgebruik door de rijksoverheid. "
                "Classificatiemodel voor gegevens, soevereiniteitsvereisten en "
                "exit-strategieën. Basis voor NDS-pijler Cloud."
            ),
            geldig_van=date(2023, 4, 1),
        )
    )
    bk_coalitie = await node_repo.create(
        CorpusNodeCreate(
            title="Regeerprogramma Kabinet-Schoof — Digitalisering",
            node_type="beleidskader",
            description=(
                "Digitaliseringspassages uit het regeerprogramma (sept 2024): "
                "oprichting Nederlandse Digitale Dienst,"
                " minder afhankelijkheid externe"
                "IT-leveranciers, AI-fabriek Noord-Nederland, Europees-autonome "
                "datacenters."
            ),
        )
    )
    bk_algo_kader = await node_repo.create(
        CorpusNodeCreate(
            title="Algoritmekader",
            node_type="beleidskader",
            description=(
                "Praktisch kader met normen, instrumenten en richtlijnen voor "
                "verantwoord gebruik van algoritmen en AI door de overheid. Vertaling "
                "van juridische vereisten naar concrete handvatten."
            ),
        )
    )

    # --- Doelen ---
    doel_digid_nieuw = await node_repo.create(
        CorpusNodeCreate(
            title="DigiD Hoog betrouwbaarheidsniveau",
            node_type="doel",
            description=(
                "Realisatie van DigiD op betrouwbaarheidsniveau 'hoog' conform eIDAS, "
                "inclusief biometrische verificatie en NFC-uitlezing "
                "identiteitsdocumenten."
            ),
        )
    )
    doel_algo_register = await node_repo.create(
        CorpusNodeCreate(
            title="1000 algoritmen geregistreerd in Algoritmeregister",
            node_type="doel",
            description=(
                "Doelstelling om per eind 2026 minimaal 1500"
                " impactvolle algoritmen van overheidsorganisaties"
                " gepubliceerd te hebben in het Algoritmeregister."
            ),
            geldig_van=date(2023, 6, 1),
        )
    )
    doel_eudiw = await node_repo.create(
        CorpusNodeCreate(
            title="Europese Digitale Identiteit Wallet (EUDIW) gereed",
            node_type="doel",
            status="concept",
            description=(
                "Nederland levert een werkende EUDIW-implementatie conform de herziene "
                "eIDAS2-verordening, uiterlijk 2027. Pilot in 2026."
            ),
            geldig_van=date(2024, 1, 1),
        )
    )
    doel_fed_data = await node_repo.create(
        CorpusNodeCreate(
            title="Federatief Datastelsel operationeel",
            node_type="doel",
            description=(
                "Het Federatief Datastelsel is operationeel met minimaal 10 use-cases "
                "waarin overheden verantwoord data delen volgens het "
                "IBDS-afsprakenstelsel."
            ),
        )
    )
    doel_vendor_reductie = await node_repo.create(
        CorpusNodeCreate(
            title="30% minder afhankelijkheid externe IT-inhuur",
            node_type="doel",
            status="concept",
            description=(
                "Rijksbreed 30% reductie in afhankelijkheid van"
                " externe IT-leveranciers door structurele"
                " versterking van interne IT-capaciteit. Onderdeel"
                "regeerprogramma."
            ),
            geldig_van=date(2024, 9, 1),
        )
    )
    doel_duurzaam_digi = await node_repo.create(
        CorpusNodeCreate(
            title="Duurzame digitalisering overheidsdatacenters",
            node_type="doel",
            description=(
                "Alle overheidsdatacenters voldoen aan de European Energy Efficiency "
                "Directive (EED) eisen en zijn klimaatneutraal in 2030."
            ),
        )
    )
    doel_bio_compliance = await node_repo.create(
        CorpusNodeCreate(
            title="100% BIO-compliance Rijksdienst",
            node_type="doel",
            description=(
                "Alle departementen en uitvoeringsorganisaties zijn volledig compliant "
                "met de Baseline Informatiebeveiliging Overheid (BIO)."
            ),
        )
    )
    doel_inclusie = await node_repo.create(
        CorpusNodeCreate(
            title="Digitale inclusie: 95% zelfredzaamheid",
            node_type="doel",
            description=(
                "95% van de burgers kan zonder hulp essentiële overheidsdiensten "
                "digitaal afnemen. Extra inzet op digibeten, ouderen en "
                "laaggeletterden."
            ),
        )
    )

    # --- Instrumenten ---
    instr_digid = await node_repo.create(
        CorpusNodeCreate(
            title="DigiD",
            node_type="instrument",
            description=(
                "Landelijke authenticatievoorziening waarmee burgers veilig inloggen "
                "bij de overheid. 15+ miljoen actieve gebruikers. Wordt doorontwikkeld "
                "naar betrouwbaarheidsniveau Hoog."
            ),
        )
    )
    instr_mijnoverheid = await node_repo.create(
        CorpusNodeCreate(
            title="MijnOverheid",
            node_type="instrument",
            description=(
                "Persoonlijk portaal waar burgers hun overheidszaken regelen: "
                "berichten, lopende zaken, persoonlijke gegevens uit basisregistraties."
            ),
        )
    )
    instr_algo_register = await node_repo.create(
        CorpusNodeCreate(
            title="Algoritmeregister (algoritmes.overheid.nl)",
            node_type="instrument",
            description=(
                "Centraal register waar overheidsorganisaties hun algoritmen "
                "publiceren. Per januari 2026 meer dan 1000 algoritmen geregistreerd. "
                "Registratie wordt wettelijk verplicht."
            ),
        )
    )
    instr_nora = await node_repo.create(
        CorpusNodeCreate(
            title="NORA (Nederlandse Overheid Referentie Architectuur)",
            node_type="instrument",
            description=(
                "Referentie-architectuur voor de digitale overheid. Biedt principes, "
                "standaarden en bouwblokken voor interoperabele overheidssystemen."
            ),
        )
    )
    instr_ndd = await node_repo.create(
        CorpusNodeCreate(
            title="Nederlandse Digitale Dienst (i.o.)",
            node_type="instrument",
            description=(
                "Nieuw op te richten compact expertorgaan met handhavingsbevoegdheid "
                "voor kwaliteitsnormen IT-projecten. Afspraak uit regeerprogramma "
                "Schoof."
            ),
        )
    )
    instr_bio = await node_repo.create(
        CorpusNodeCreate(
            title="Baseline Informatiebeveiliging Overheid (BIO)",
            node_type="instrument",
            description=(
                "Normenkader voor informatiebeveiliging bij de overheid. Gebaseerd op "
                "ISO 27001/27002. Compliance wordt periodiek geaudit door de ADR."
            ),
        )
    )
    instr_eidas_wallet = await node_repo.create(
        CorpusNodeCreate(
            title="EUDIW Pilot Nederland",
            node_type="instrument",
            description=(
                "Nederlandse pilot voor de Europese Digitale Identiteit Wallet. Testen "
                "van use-cases zoals leeftijdsverificatie, diploma's en overheidsinlog."
            ),
        )
    )
    instr_cio_overleg = await node_repo.create(
        CorpusNodeCreate(
            title="CIO-Overleg Rijksdienst",
            node_type="instrument",
            description=(
                "Overlegorgaan van departementale CIO's, voorgezeten door CIO Rijk. "
                "Bespreekt cloudbeleid, GenAI governance, cyberveiligheid en "
                "I-strategie."
            ),
        )
    )

    # --- Maatregelen ---
    maatr_algo_verpl = await node_repo.create(
        CorpusNodeCreate(
            title="Verplichte registratie impactvolle algoritmen",
            node_type="maatregel",
            description=(
                "Wettelijk verplichten van publicatie van impactvolle en hoog-risico "
                "algoritmen in het Algoritmeregister, inclusief handhaving door de ADR."
            ),
        )
    )
    maatr_cloud_exit = await node_repo.create(
        CorpusNodeCreate(
            title="Cloud exit-strategie verplicht stellen",
            node_type="maatregel",
            description=(
                "Rijksorganisaties moeten bij cloudcontracten een exit-strategie "
                "opstellen en periodiek testen. Doel: voorkomen vendor lock-in."
            ),
        )
    )
    maatr_digid_upgrade = await node_repo.create(
        CorpusNodeCreate(
            title="DigiD upgrade naar betrouwbaarheidsniveau Hoog",
            node_type="maatregel",
            description=(
                "Technische en organisatorische maatregelen om DigiD op eIDAS-niveau "
                "Hoog te brengen, inclusief gezichtherkenning en NFC-chip uitlezing."
            ),
        )
    )
    maatr_it_inhuur = await node_repo.create(
        CorpusNodeCreate(
            title="Programma Minder Externe IT-Inhuur",
            node_type="maatregel",
            description=(
                "Rijksbreed programma om 30% van externe IT-rollen om te zetten naar "
                "vast personeel. Concurrentiegerichte salarisschalen, "
                "traineeprogramma's en doorstroom."
            ),
        )
    )
    maatr_wdo_transitie = await node_repo.create(
        CorpusNodeCreate(
            title="WDO Transitieprogramma",
            node_type="maatregel",
            description=(
                "Begeleiding van overheidsorganisaties bij implementatie van de Wet "
                "Digitale Overheid. Verlengde overgangstermijn tot 1 juli 2028."
            ),
        )
    )
    maatr_genai = await node_repo.create(
        CorpusNodeCreate(
            title="Generatieve AI Richtlijn Rijksoverheid",
            node_type="maatregel",
            description=(
                "Kader voor verantwoord gebruik van generatieve AI (ChatGPT, Copilot "
                "etc.) door rijksambtenaren. Lokale hosting-eis, classificatie van "
                "use-cases, governance."
            ),
        )
    )
    maatr_data_spaces = await node_repo.create(
        CorpusNodeCreate(
            title="Aansluiting Europese Data Spaces",
            node_type="maatregel",
            description=(
                "Nederlandse overheid sluit aan bij Europese data spaces voor "
                "gezondheid, mobiliteit en overheid. Implementatie via "
                "IBDS-afsprakenstelsel."
            ),
        )
    )

    # --- Politieke Input ---
    pi_motie_sixdijkstra = await node_repo.create(
        CorpusNodeCreate(
            title="Motie Six Dijkstra (NSC) — AI lokaal draaien",
            node_type="politieke_input",
            description=(
                "Aangenomen motie: AI-modellen die de overheid gebruikt moeten in "
                "beginsel lokaal op overheidssystemen draaien om datalekrisico's te "
                "minimaliseren."
            ),
        )
    )
    pi_motie_veldhoen = await node_repo.create(
        CorpusNodeCreate(
            title="Motie Veldhoen (GL-PvdA) — Algoritmen in wetgeving",
            node_type="politieke_input",
            description=(
                "Aangenomen motie in de Eerste Kamer: bij het wetgevingsproces moet "
                "expliciet worden vastgelegd welke algoritmen worden gebruikt voor "
                "uitvoering."
            ),
        )
    )
    pi_kamervraag_digid = await node_repo.create(
        CorpusNodeCreate(
            title="Kamervragen over DigiD-storingen (december 2025)",
            node_type="politieke_input",
            description=(
                "Schriftelijke vragen van Kamerleden over herhaalde DigiD-storingen en "
                "de impact op burgers die afhankelijk zijn van digitale "
                "dienstverlening."
            ),
        )
    )
    pi_kamervraag_cloud = await node_repo.create(
        CorpusNodeCreate(
            title="Kamervragen over cloudafhankelijkheid Microsoft",
            node_type="politieke_input",
            description=(
                "Vragen over de afhankelijkheid van de rijksoverheid van Microsoft "
                "Azure en Office 365. Gevraagd naar soevereine alternatieven en "
                "exit-opties."
            ),
        )
    )
    pi_planningsbrief = await node_repo.create(
        CorpusNodeCreate(
            title="Planningsbrief Digitalisering 2026",
            node_type="politieke_input",
            description=(
                "Kamerbrief (13 jan 2026) met de digitale agenda voor 2026: NDS "
                "voortgang, AI Act implementatie, CIO-stelsel, EUDIW pilot, "
                "Algoritmeregister verplichtingen."
            ),
        )
    )
    pi_verzamelbrief_q4 = await node_repo.create(
        CorpusNodeCreate(
            title="Verzamelbrief Digitalisering december 2025",
            node_type="politieke_input",
            description=(
                "Kwartaalbrief aan de Tweede Kamer met voortgang op alle "
                "digitaliseringsonderwerpen: NDS, IBDS, WDO, algoritmen, "
                "cyberveiligheid en digitale inclusie."
            ),
        )
    )
    pi_debat_diza = await node_repo.create(
        CorpusNodeCreate(
            title="Commissiedebat Digitale Zaken — februari 2026",
            node_type="politieke_input",
            description=(
                "Aanstaand commissiedebat DiZa over NDS"
                " voortgang, AI Act implementatie en de"
                " oprichting van de Nederlandse Digitale Dienst."
            ),
        )
    )
    pi_motie_digi_dienst = await node_repo.create(
        CorpusNodeCreate(
            title="Motie Rajkowski (VVD) — Versnelling Nederlandse Digitale Dienst",
            node_type="politieke_input",
            description=(
                "Motie die de regering verzoekt de oprichting van de Nederlandse "
                "Digitale Dienst te versnellen en voor Q3 2026 operationeel te maken."
            ),
        )
    )
    pi_ek_deskundigen = await node_repo.create(
        CorpusNodeCreate(
            title="Deskundigenbijeenkomst Eerste Kamer — NDS",
            node_type="politieke_input",
            description=(
                "Bijeenkomst van de Eerste Kamer commissie Digitalisering (DIGI) met "
                "experts over de haalbaarheid en financiering van de Nederlandse "
                "Digitaliseringsstrategie."
            ),
        )
    )

    # --- Problemen (Drivers) ---
    prob_digitale_kloof = await node_repo.create(
        CorpusNodeCreate(
            title="Digitale kloof in overheidsdienstverlening",
            node_type="probleem",
            description=(
                "Circa 4 miljoen Nederlanders zijn onvoldoende digitaal vaardig om "
                "zelfstandig overheidsdiensten digitaal te gebruiken. Dit leidt tot "
                "ongelijke toegang tot voorzieningen."
            ),
        )
    )
    prob_vendor_lock = await node_repo.create(
        CorpusNodeCreate(
            title="Afhankelijkheid externe IT-leveranciers",
            node_type="probleem",
            description=(
                "De rijksoverheid is sterk afhankelijk van een beperkt aantal grote "
                "IT-leveranciers (Microsoft, SAP, Oracle). Dit creëert lock-in "
                "risico's, hoge kosten en verminderde soevereiniteit."
            ),
        )
    )
    prob_algo_bias = await node_repo.create(
        CorpusNodeCreate(
            title="Risico op algoritmische discriminatie",
            node_type="probleem",
            description=(
                "Onvoldoende toezicht en transparantie bij overheidsalgoritmen kan "
                "leiden tot discriminatie en aantasting van grondrechten, zoals "
                "gebleken bij de toeslagenaffaire."
            ),
        )
    )
    prob_data_silo = await node_repo.create(
        CorpusNodeCreate(
            title="Gefragmenteerd datalandschap overheid",
            node_type="probleem",
            description=(
                "Data bij de overheid zit verspreid over honderden organisaties en "
                "systemen. Dit belemmert interbestuurlijke"
                " samenwerking, beleidsanalyse"
                "en dienstverlening."
            ),
        )
    )
    prob_cyber_dreiging = await node_repo.create(
        CorpusNodeCreate(
            title="Toenemende cyberdreiging overheid",
            node_type="probleem",
            description=(
                "Statelijke actoren en cybercriminelen richten zich steeds meer op "
                "overheidsorganisaties. BIO-compliance is"
                " onvoldoende en bewustzijn van"
                "medewerkers is wisselend."
            ),
        )
    )

    # --- Effecten (Outcomes) ---
    eff_digid_bereik = await node_repo.create(
        CorpusNodeCreate(
            title="Verhoogd betrouwbaarheidsniveau digitale identiteit",
            node_type="effect",
            description=(
                "Door DigiD Hoog en EUDIW beschikken burgers over identiteitsmiddelen "
                "op betrouwbaarheidsniveau hoog, waardoor meer"
                " diensten veilig digitaal"
                "afgehandeld kunnen worden."
            ),
        )
    )
    eff_algo_transparant = await node_repo.create(
        CorpusNodeCreate(
            title="Transparantie overheidsalgoritmen gerealiseerd",
            node_type="effect",
            description=(
                "Alle impactvolle overheidsalgoritmen zijn gepubliceerd in het "
                "Algoritmeregister, waardoor burgers en toezichthouders inzicht hebben "
                "in algoritmische besluitvorming."
            ),
        )
    )
    eff_data_beschikbaar = await node_repo.create(
        CorpusNodeCreate(
            title="Interbestuurlijke data beschikbaar via Federatief Datastelsel",
            node_type="effect",
            description=(
                "Via het Federatief Datastelsel kunnen overheidsorganisaties op een "
                "gestandaardiseerde en veilige manier data uitwisselen voor betere "
                "dienstverlening en beleid."
            ),
        )
    )
    eff_minder_inhuur = await node_repo.create(
        CorpusNodeCreate(
            title="Reductie externe IT-inhuur met 20%",
            node_type="effect",
            description=(
                "Door gericht wervingsbeleid en betere arbeidsvoorwaarden is het "
                "aandeel externe IT-inhuur bij de rijksoverheid met 20% gedaald ten "
                "opzichte van 2024."
            ),
        )
    )

    # --- Beleidsopties (Courses of Action) ---
    bo_wallet_native = await node_repo.create(
        CorpusNodeCreate(
            title="Beleidsoptie: EUDIW als native app",
            node_type="beleidsoptie",
            description=(
                "De Nederlandse EUDIW wallet wordt als native app (iOS/Android) "
                "ontwikkeld. Voordelen: betere beveiliging en hardware-integratie. "
                "Nadeel: hogere ontwikkel- en onderhoudskosten."
            ),
        )
    )
    bo_wallet_pwa = await node_repo.create(
        CorpusNodeCreate(
            title="Beleidsoptie: EUDIW als Progressive Web App",
            node_type="beleidsoptie",
            description=(
                "De Nederlandse EUDIW wallet wordt als PWA ontwikkeld. Voordelen: "
                "platform-onafhankelijk, lagere kosten. Nadeel: beperktere toegang tot "
                "hardware (NFC, biometrie)."
            ),
        )
    )
    bo_algo_zelfregulering = await node_repo.create(
        CorpusNodeCreate(
            title="Beleidsoptie: Algoritmeregistratie via zelfregulering",
            node_type="beleidsoptie",
            description=(
                "Overheidsorganisaties registreren algoritmen vrijwillig op basis van "
                "richtlijnen. Voordelen: snel te implementeren, weinig regeldruk. "
                "Nadeel: onvoldoende compliance zonder wettelijke basis."
            ),
            status="afgewezen",
        )
    )
    bo_algo_wettelijk = await node_repo.create(
        CorpusNodeCreate(
            title="Beleidsoptie: Wettelijk verplichte algoritmeregistratie",
            node_type="beleidsoptie",
            description=(
                "Algoritmeregistratie wordt wettelijk verplicht via AMvB. Voordelen: "
                "volledige dekking, handhaafbaar. Nadeel: langere implementatietijd, "
                "hogere uitvoeringslasten."
            ),
            status="gekozen",
        )
    )
    bo_cloud_soeverein = await node_repo.create(
        CorpusNodeCreate(
            title="Beleidsoptie: Soevereine overheidscloud",
            node_type="beleidsoptie",
            description=(
                "De rijksoverheid bouwt een eigen soevereine cloudinfrastructuur. "
                "Voordelen: volledige controle, geen lock-in."
                " Nadeel: zeer hoge kosten,"
                "beperkte innovatiesnelheid."
            ),
        )
    )

    print(f"  Corpus: {61} nodes aangemaakt")

    # =========================================================================
    # 4b. TEMPORAL HISTORY — simulate realistic title/status changes
    # =========================================================================

    # Dossier AI: created as "AI-regulering" (2023-06), renamed to current (2025-01)
    await node_repo.update(
        dos_ai.id,
        CorpusNodeUpdate(
            title="Dossier AI en Algoritmen",
            wijzig_datum=date(2025, 1, 15),
        ),
    )

    # WDO: created as concept (2021-03), became actief (2023-07)
    await node_repo.update(
        bk_wdo.id,
        CorpusNodeUpdate(
            status="actief",
            wijzig_datum=date(2023, 7, 1),
        ),
    )

    # Cloudbeleid: created as concept title (2023-04), finalized (2024-01)
    await node_repo.update(
        bk_cloudbeleid.id,
        CorpusNodeUpdate(
            title="Rijksbreed Cloudbeleid 2024",
            wijzig_datum=date(2024, 1, 15),
        ),
    )

    # EUDIW doel: created as concept (2024-01), became actief (2025-03)
    await node_repo.update(
        doel_eudiw.id,
        CorpusNodeUpdate(
            status="actief",
            wijzig_datum=date(2025, 3, 1),
        ),
    )

    # Algoritmeregister doel: target raised from 1000 (2023-06) to 1500 (2025-06)
    await node_repo.update(
        doel_algo_register.id,
        CorpusNodeUpdate(
            title="1500 algoritmen geregistreerd in Algoritmeregister",
            wijzig_datum=date(2025, 6, 1),
        ),
    )

    # Vendor reductie: created as concept (2024-09), became actief (2025-01)
    await node_repo.update(
        doel_vendor_reductie.id,
        CorpusNodeUpdate(
            status="actief",
            wijzig_datum=date(2025, 1, 1),
        ),
    )

    print("  Temporeel: 6 historische wijzigingen aangemaakt")

    # =========================================================================
    # 5. EDGES
    # =========================================================================

    edges_data = [
        # NDS relaties
        (
            bk_nds,
            dos_digi_overheid,
            "onderdeel_van",
            "NDS is het overkoepelende kader voor digitale overheid",
        ),
        (
            bk_nds,
            dos_digi_samenleving,
            "onderdeel_van",
            "NDS adresseert ook de digitale samenleving",
        ),
        (
            bk_nds,
            dos_cio_rijk,
            "onderdeel_van",
            "NDS bevat pijlers voor cloud en ICT-governance",
        ),
        (
            bk_nds,
            bk_coalitie,
            "vloeit_voort_uit",
            "NDS geeft invulling aan digitaliseringsambities regeerprogramma",
        ),
        (
            bk_nds,
            bk_ibds,
            "verwijst_naar",
            "NDS bouwt voort op de Interbestuurlijke Datastrategie",
        ),
        # Coalitieakkoord → doelen en instrumenten
        (
            bk_coalitie,
            instr_ndd,
            "vereist",
            "Regeerprogramma kondigt oprichting NDD aan",
        ),
        (
            bk_coalitie,
            doel_vendor_reductie,
            "draagt_bij_aan",
            "Regeerprogramma stelt doel minder IT-inhuur",
        ),
        (
            bk_coalitie,
            maatr_it_inhuur,
            "vereist",
            "Regeerprogramma leidt tot programma minder externe IT-inhuur",
        ),
        # WDO relaties
        (bk_wdo, instr_digid, "vereist", "WDO stelt veiligheidseisen aan DigiD"),
        (
            bk_wdo,
            maatr_wdo_transitie,
            "implementeert",
            "Transitieprogramma implementeert WDO-eisen",
        ),
        (
            bk_wdo,
            dos_digi_overheid,
            "onderdeel_van",
            "WDO is onderdeel van dossier Digitale Overheid",
        ),
        # DigiD keten
        (
            instr_digid,
            doel_digid_nieuw,
            "draagt_bij_aan",
            "DigiD wordt opgewaardeerd naar niveau Hoog",
        ),
        (
            maatr_digid_upgrade,
            doel_digid_nieuw,
            "implementeert",
            "Upgrade realiseert DigiD Hoog",
        ),
        (
            maatr_digid_upgrade,
            instr_digid,
            "draagt_bij_aan",
            "Technische verbetering van DigiD",
        ),
        (
            pi_kamervraag_digid,
            instr_digid,
            "evalueert",
            "Kamervragen evalueren DigiD-beschikbaarheid",
        ),
        # EUDIW keten
        (
            instr_eidas_wallet,
            doel_eudiw,
            "draagt_bij_aan",
            "Pilot levert bewijs voor EUDIW-haalbaarheid",
        ),
        (
            doel_eudiw,
            bk_wdo,
            "vloeit_voort_uit",
            "EUDIW bouwt voort op WDO-authenticatie-eisen",
        ),
        (
            doel_eudiw,
            bk_nds,
            "vloeit_voort_uit",
            "EUDIW is onderdeel NDS-pijler dienstverlening",
        ),
        # AI en Algoritmen keten
        (bk_ai_act, dos_ai, "onderdeel_van", "AI Act is kerninstrument in AI-dossier"),
        (
            bk_ai_act,
            maatr_algo_verpl,
            "vereist",
            "AI Act vereist verplichte registratie hoog-risico algoritmen",
        ),
        (
            bk_ai_act,
            bk_algo_kader,
            "implementeert",
            "Algoritmekader vertaalt AI Act naar praktijk",
        ),
        (
            bk_algo_kader,
            instr_algo_register,
            "vereist",
            "Algoritmekader verwijst naar Algoritmeregister",
        ),
        (
            instr_algo_register,
            doel_algo_register,
            "draagt_bij_aan",
            "Register is het instrument om registratiedoel te halen",
        ),
        (
            maatr_algo_verpl,
            doel_algo_register,
            "draagt_bij_aan",
            "Verplichting versnelt registratieaantallen",
        ),
        (
            pi_motie_veldhoen,
            bk_algo_kader,
            "evalueert",
            "Motie vraagt om algoritmen in wetgevingsproces",
        ),
        (
            pi_motie_sixdijkstra,
            maatr_genai,
            "evalueert",
            "Motie beïnvloedt GenAI richtlijn: lokaal draaien",
        ),
        # Data keten
        (
            bk_ibds,
            doel_fed_data,
            "draagt_bij_aan",
            "IBDS stuurt aan op operationeel Federatief Datastelsel",
        ),
        (bk_ibds, dos_data, "onderdeel_van", "IBDS is kerndocument in data-dossier"),
        (
            maatr_data_spaces,
            doel_fed_data,
            "draagt_bij_aan",
            "EU Data Spaces aansluiting versterkt Federatief Datastelsel",
        ),
        (
            maatr_data_spaces,
            bk_ibds,
            "vloeit_voort_uit",
            "Data Spaces zijn logische stap vanuit IBDS",
        ),
        # CIO Rijk keten
        (
            bk_cio_stelsel,
            dos_cio_rijk,
            "onderdeel_van",
            "CIO-stelsel is kern van ICT-governance dossier",
        ),
        (
            bk_cio_stelsel,
            instr_cio_overleg,
            "implementeert",
            "CIO-stelsel regelt CIO-Overleg bevoegdheden",
        ),
        (
            bk_cloudbeleid,
            maatr_cloud_exit,
            "vereist",
            "Cloudbeleid vereist exit-strategieën",
        ),
        (
            bk_cloudbeleid,
            dos_cio_rijk,
            "onderdeel_van",
            "Cloudbeleid valt onder CIO Rijk dossier",
        ),
        (
            pi_kamervraag_cloud,
            bk_cloudbeleid,
            "evalueert",
            "Kamervragen evalueren cloudafhankelijkheid",
        ),
        (
            instr_bio,
            doel_bio_compliance,
            "draagt_bij_aan",
            "BIO is het normenkader voor 100% compliance",
        ),
        (
            instr_nora,
            bk_cio_stelsel,
            "draagt_bij_aan",
            "NORA geeft architectuurkaders voor CIO-stelsel",
        ),
        (
            maatr_genai,
            bk_cio_stelsel,
            "vloeit_voort_uit",
            "GenAI richtlijn opgesteld binnen CIO-stelsel governance",
        ),
        # NDD keten
        (
            instr_ndd,
            dos_digi_overheid,
            "onderdeel_van",
            "NDD wordt onderdeel van digitale overheid",
        ),
        (
            pi_motie_digi_dienst,
            instr_ndd,
            "evalueert",
            "Motie dringt aan op versnelling oprichting NDD",
        ),
        # Inclusie
        (
            doel_inclusie,
            dos_digi_samenleving,
            "onderdeel_van",
            "Digitale inclusie valt onder dossier Digitale Samenleving",
        ),
        (
            doel_inclusie,
            bk_nds,
            "vloeit_voort_uit",
            "Inclusiedoel komt voort uit NDS-pijler dienstverlening",
        ),
        (
            instr_mijnoverheid,
            doel_inclusie,
            "draagt_bij_aan",
            "MijnOverheid draagt bij aan zelfredzaamheid burgers",
        ),
        # Vendor reductie
        (
            doel_vendor_reductie,
            dos_cio_rijk,
            "onderdeel_van",
            "Vendor reductie is CIO Rijk agendapunt",
        ),
        (
            maatr_it_inhuur,
            doel_vendor_reductie,
            "implementeert",
            "Inhuurprogramma realiseert reductiedoel",
        ),
        # Duurzaamheid
        (
            doel_duurzaam_digi,
            bk_cloudbeleid,
            "vloeit_voort_uit",
            "Duurzaamheidsdoel hangt samen met cloudbeleid",
        ),
        (
            doel_duurzaam_digi,
            bk_nds,
            "vloeit_voort_uit",
            "NDS benoemt duurzame digitalisering",
        ),
        # Politieke input → overkoepelend
        (
            pi_planningsbrief,
            bk_nds,
            "verwijst_naar",
            "Planningsbrief beschrijft NDS-voortgang",
        ),
        (
            pi_planningsbrief,
            bk_ai_act,
            "verwijst_naar",
            "Planningsbrief noemt AI Act implementatie",
        ),
        (
            pi_verzamelbrief_q4,
            bk_nds,
            "verwijst_naar",
            "Verzamelbrief rapporteert over NDS",
        ),
        (
            pi_verzamelbrief_q4,
            bk_wdo,
            "verwijst_naar",
            "Verzamelbrief rapporteert over WDO-voortgang",
        ),
        (
            pi_debat_diza,
            pi_planningsbrief,
            "verwijst_naar",
            "Debat gaat over onderwerpen uit planningsbrief",
        ),
        (
            pi_ek_deskundigen,
            bk_nds,
            "evalueert",
            "Eerste Kamer evalueert NDS haalbaarheid",
        ),
        # Probleem → Doel (leidt_tot)
        (
            prob_digitale_kloof,
            doel_inclusie,
            "leidt_tot",
            "Digitale kloof motiveert inclusiedoelstellingen",
        ),
        (
            prob_vendor_lock,
            doel_vendor_reductie,
            "leidt_tot",
            "Vendor lock-in probleem leidt tot reductiedoelstelling",
        ),
        (
            prob_algo_bias,
            doel_algo_register,
            "leidt_tot",
            "Risico op discriminatie motiveert algoritmeregistratie",
        ),
        (
            prob_data_silo,
            doel_fed_data,
            "leidt_tot",
            "Datafragmentatie motiveert Federatief Datastelsel",
        ),
        (
            prob_cyber_dreiging,
            doel_bio_compliance,
            "leidt_tot",
            "Cyberdreiging motiveert 100% BIO-compliance",
        ),
        # Maatregel/Instrument adresseert Probleem
        (
            instr_mijnoverheid,
            prob_digitale_kloof,
            "adresseert",
            "MijnOverheid adresseert toegankelijkheid overheidsdiensten",
        ),
        (
            maatr_it_inhuur,
            prob_vendor_lock,
            "adresseert",
            "Inhuurreductie adresseert leveranciersafhankelijkheid",
        ),
        (
            maatr_algo_verpl,
            prob_algo_bias,
            "adresseert",
            "Verplichte registratie adresseert algoritmisch risico",
        ),
        (
            maatr_data_spaces,
            prob_data_silo,
            "adresseert",
            "Data Spaces adresseren gefragmenteerd datalandschap",
        ),
        (
            instr_bio,
            prob_cyber_dreiging,
            "adresseert",
            "BIO adresseert cyberdreiging bij overheid",
        ),
        # Maatregel → Effect (leidt_tot)
        (
            maatr_digid_upgrade,
            eff_digid_bereik,
            "leidt_tot",
            "DigiD Hoog upgrade leidt tot hoger betrouwbaarheidsniveau",
        ),
        (
            maatr_algo_verpl,
            eff_algo_transparant,
            "leidt_tot",
            "Verplichte registratie leidt tot algoritmetransparantie",
        ),
        (
            maatr_data_spaces,
            eff_data_beschikbaar,
            "leidt_tot",
            "Data Spaces leiden tot beschikbare interbestuurlijke data",
        ),
        (
            maatr_it_inhuur,
            eff_minder_inhuur,
            "leidt_tot",
            "Inhuurprogramma leidt tot 20% reductie externe IT-inhuur",
        ),
        # Effect meet Doel
        (
            eff_algo_transparant,
            doel_algo_register,
            "meet",
            "Algoritmtransparantie meet registratiedoelstelling",
        ),
        (
            eff_data_beschikbaar,
            doel_fed_data,
            "meet",
            "Data-beschikbaarheid meet FDS-doelstelling",
        ),
        (
            eff_minder_inhuur,
            doel_vendor_reductie,
            "meet",
            "Inhuurreductie meet vendor-reductiedoel",
        ),
        (
            eff_digid_bereik,
            doel_digid_nieuw,
            "meet",
            "Betrouwbaarheidsniveau meet DigiD Hoog doel",
        ),
        # Beleidsoptie → Doel (draagt_bij_aan)
        (
            bo_wallet_native,
            doel_eudiw,
            "draagt_bij_aan",
            "Native app-optie draagt bij aan EUDIW-doel",
        ),
        (
            bo_wallet_pwa,
            doel_eudiw,
            "draagt_bij_aan",
            "PWA-optie draagt bij aan EUDIW-doel",
        ),
        (
            bo_algo_wettelijk,
            doel_algo_register,
            "draagt_bij_aan",
            "Wettelijke verplichting draagt bij aan registratiedoel",
        ),
        (
            bo_algo_zelfregulering,
            doel_algo_register,
            "draagt_bij_aan",
            "Zelfregulering draagt bij aan registratiedoel",
        ),
        (
            bo_cloud_soeverein,
            doel_vendor_reductie,
            "draagt_bij_aan",
            "Soevereine cloud draagt bij aan vendorreductie",
        ),
        # Probleem → Dossier (onderdeel_van)
        (
            prob_digitale_kloof,
            dos_digi_overheid,
            "onderdeel_van",
            "Digitale kloof is kernprobleem in digitale overheid",
        ),
        (
            prob_vendor_lock,
            dos_cio_rijk,
            "onderdeel_van",
            "Vendor lock-in is probleem in CIO Rijk dossier",
        ),
        (
            prob_algo_bias,
            dos_ai,
            "onderdeel_van",
            "Algoritmische discriminatie is kernprobleem in AI-dossier",
        ),
        (
            prob_data_silo,
            dos_data,
            "onderdeel_van",
            "Datafragmentatie is kernprobleem in data-dossier",
        ),
    ]

    for from_node, to_node, edge_type_id, description in edges_data:
        await edge_repo.create(
            EdgeCreate(
                from_node_id=from_node.id,
                to_node_id=to_node.id,
                edge_type_id=edge_type_id,
                description=description,
            )
        )

    print(f"  Edges: {len(edges_data)} relaties aangemaakt")

    # =========================================================================
    # 6. TASKS
    # =========================================================================

    tasks_data = [
        # --- DigiD / Identiteit ---
        # (node, title, description, assignee, status, priority, deadline,
        #  organisatie_eenheid, subtasks)
        # subtasks: list of (title, assignee, status, priority, deadline)
        (
            maatr_digid_upgrade,
            "Technische analyse DigiD NFC-chip uitlezing",
            (
                "Inventariseer technische mogelijkheden en beperkingen van "
                "NFC-uitlezing van identiteitsdocumenten voor DigiD Hoog."
            ),
            pm("p_nguyen"),
            "in_progress",
            "hoog",
            date(2026, 3, 15),
            afd_id_toegang,
            [
                (
                    "Inventarisatie NFC-chip types in omloop",
                    pm("p_nguyen"),
                    "done",
                    "normaal",
                    date(2026, 2, 15),
                ),
                (
                    "Test NFC-uitlezing op Android-toestellen",
                    pm("p_nguyen"),
                    "in_progress",
                    "hoog",
                    date(2026, 3, 1),
                ),
                (
                    "Test NFC-uitlezing op iOS-toestellen",
                    None,
                    "open",
                    "hoog",
                    date(2026, 3, 10),
                ),
            ],
        ),
        (
            maatr_digid_upgrade,
            "Privacytoets DigiD gezichtsherkenning",
            (
                "Voer een DPIA uit op de inzet van gezichtsherkenning bij DigiD Hoog "
                "authenticatie."
            ),
            pm("p_kaya"),
            "open",
            "hoog",
            date(2026, 4, 1),
            afd_id_toegang,
            [],
        ),
        (
            pi_kamervraag_digid,
            "Beantwoording Kamervragen DigiD-storingen",
            (
                "Stel concept-antwoorden op voor de Kamervragen over DigiD-storingen "
                "december 2025."
            ),
            pm("p_nguyen"),
            "done",
            "kritiek",
            date(2026, 1, 20),
            afd_id_toegang,
            [],
        ),
        (
            instr_digid,
            "Kwartaalrapportage DigiD Q4 2025",
            (
                "Stel de kwartaalrapportage op met gebruikscijfers, beschikbaarheid en "
                "incidenten DigiD Q4."
            ),
            pm("p_nguyen"),
            "done",
            "normaal",
            date(2026, 1, 31),
            afd_id_toegang,
            [],
        ),
        # Unassigned task for coordinator workflow demo
        (
            instr_digid,
            "DigiD beveiligingsreview Q1 2026",
            (
                "Coördineer de periodieke beveiligingsreview van DigiD-infrastructuur "
                "met Logius en NCSC."
            ),
            None,
            "open",
            "hoog",
            date(2026, 3, 31),
            afd_id_toegang,
            [],
        ),
        # --- EUDIW ---
        (
            instr_eidas_wallet,
            "Opzetten EUDIW pilot use-cases",
            (
                "Definieer 3 pilot use-cases voor de Nederlandse EUDIW: "
                "leeftijdsverificatie, diploma's en overheidsinlog."
            ),
            pm("p_kaya"),
            "in_progress",
            "hoog",
            date(2026, 6, 1),
            afd_id_toegang,
            [],
        ),
        (
            doel_eudiw,
            "Architectuurbesluit EUDIW wallet-app",
            (
                "Neem een architectuurbesluit over de technische opzet van de "
                "Nederlandse wallet-app (native vs. PWA)."
            ),
            pm("p_smit"),
            "open",
            "hoog",
            date(2026, 4, 15),
            afd_id_toegang,
            [],
        ),
        # --- WDO ---
        (
            maatr_wdo_transitie,
            "Handreiking WDO-compliance opstellen",
            (
                "Schrijf een praktische handreiking voor"
                " uitvoeringsorganisaties om aan"
                " WDO-vereisten te voldoen."
            ),
            pm("p_ah_wdo"),
            "in_progress",
            "normaal",
            date(2026, 5, 1),
        ),
        (
            bk_wdo,
            "Juridische analyse verlengde overgangstermijn",
            (
                "Analyseer de juridische implicaties van de verlengde "
                "WDO-overgangstermijn tot 1 juli 2028."
            ),
            pm("p_achterberg"),
            "done",
            "normaal",
            date(2026, 1, 15),
        ),
        # --- MijnOverheid ---
        (
            instr_mijnoverheid,
            "MijnOverheid gebruikerstevredenheidsonderzoek",
            (
                "Voer het jaarlijkse gebruikersonderzoek uit en rapporteer resultaten "
                "met aanbevelingen."
            ),
            pm("p_visser"),
            "open",
            "normaal",
            date(2026, 4, 30),
        ),
        (
            instr_mijnoverheid,
            "MijnOverheid toegankelijkheidsaudit WCAG 2.2",
            (
                "Laat een externe audit uitvoeren op WCAG 2.2 AA-compliance van "
                "MijnOverheid."
            ),
            pm("p_visser"),
            "open",
            "hoog",
            date(2026, 3, 31),
        ),
        # --- AI en Algoritmen ---
        (
            maatr_algo_verpl,
            "AMvB verplichte algoritmeregistratie opstellen",
            (
                "Stel de concept-AMvB op die publicatie van impactvolle algoritmen "
                "wettelijk verplicht."
            ),
            pm("p_dejong"),
            "in_progress",
            "kritiek",
            date(2026, 6, 30),
            afd_ai_data,
            [],
        ),
        (
            instr_algo_register,
            "Algoritmeregister doorontwikkeling v2.0",
            (
                "Coördineer de doorontwikkeling met verbeterde zoekfunctie, "
                "impactclassificatie en API-koppeling."
            ),
            pm("p_bakker"),
            "in_progress",
            "hoog",
            date(2026, 5, 15),
            afd_ai_data,
            [],
        ),
        (
            bk_ai_act,
            "Implementatieplan AI Act hoog-risico systemen",
            (
                "Stel een interdepartementaal implementatieplan op voor AI Act "
                "verplichtingen per augustus 2026."
            ),
            pm("p_dejong"),
            "open",
            "kritiek",
            date(2026, 3, 1),
            afd_ai_data,
            [],
        ),
        (
            pi_motie_veldhoen,
            "Advies algoritmen in wetgevingsproces",
            (
                "Schrijf een beleidsadvies hoe algoritmen"
                " structureel meegenomen kunnen worden"
                " in het wetgevingsproces."
            ),
            pm("p_dejong"),
            "open",
            "normaal",
            date(2026, 5, 1),
        ),
        (
            maatr_genai,
            "Update GenAI richtlijn na motie Six Dijkstra",
            (
                "Verwerk de motie Six Dijkstra (lokaal draaien) in een geactualiseerde "
                "versie van de GenAI richtlijn."
            ),
            pm("p_bakker"),
            "open",
            "hoog",
            date(2026, 3, 15),
        ),
        # --- Data ---
        (
            doel_fed_data,
            "Selectie 10 use-cases Federatief Datastelsel",
            (
                "Selecteer in overleg met VNG en IPO 10 concrete use-cases voor het "
                "Federatief Datastelsel."
            ),
            pm("p_kumar"),
            "in_progress",
            "hoog",
            date(2026, 4, 1),
        ),
        (
            maatr_data_spaces,
            "Verkenning aansluiting EU Health Data Space",
            (
                "Verken met VWS de technische en juridische vereisten voor aansluiting "
                "op de European Health Data Space."
            ),
            pm("p_kumar"),
            "open",
            "normaal",
            date(2026, 6, 1),
        ),
        (
            bk_ibds,
            "IBDS voortgangsrapportage Tweede Kamer",
            "Stel de halfjaarlijkse voortgangsrapportage IBDS op voor de Tweede Kamer.",
            pm("p_kumar"),
            "open",
            "normaal",
            date(2026, 5, 15),
        ),
        # --- CIO Rijk / Cloud ---
        (
            bk_cloudbeleid,
            "Cloud classificatiemodel actualisering",
            (
                "Actualiseer het cloud classificatiemodel met nieuwe categorieën voor "
                "GenAI-workloads en soevereine cloud."
            ),
            pm("p_devries"),
            "in_progress",
            "hoog",
            date(2026, 4, 15),
        ),
        (
            maatr_cloud_exit,
            "Template exit-strategie cloudcontracten",
            (
                "Ontwikkel een standaard template voor exit-strategieën bij "
                "cloudcontracten voor gebruik door alle departementen."
            ),
            pm("p_devries"),
            "open",
            "normaal",
            date(2026, 5, 1),
        ),
        (
            pi_kamervraag_cloud,
            "Beantwoording Kamervragen Microsoft-afhankelijkheid",
            (
                "Stel concept-antwoorden op voor de Kamervragen over Microsoft "
                "Azure/O365-afhankelijkheid."
            ),
            pm("p_devries"),
            "done",
            "kritiek",
            date(2026, 2, 1),
        ),
        (
            bk_cio_stelsel,
            "Implementatie CIO-stelsel 2026: nieuwe rollen",
            (
                "Begeleid de benoeming van CDO, CPO en CTO bij alle departementen "
                "conform het nieuwe CIO-stelsel."
            ),
            pm("p_dir_cio"),
            "in_progress",
            "hoog",
            date(2026, 6, 30),
        ),
        (
            instr_cio_overleg,
            "Voorbereiding CIO-Overleg maart 2026",
            (
                "Stel de agenda op voor het CIO-Overleg met onderwerpen: GenAI "
                "governance, cloud soevereiniteit en BIO-voortgang."
            ),
            pm("p_smit"),
            "open",
            "normaal",
            date(2026, 2, 28),
        ),
        # --- Informatiebeveiliging ---
        (
            instr_bio,
            "BIO-compliance nulmeting 2026",
            (
                "Voer de jaarlijkse nulmeting BIO-compliance uit bij alle ministeries "
                "en rapporteer gaps."
            ),
            pm("p_berg"),
            "open",
            "hoog",
            date(2026, 3, 31),
        ),
        (
            doel_bio_compliance,
            "Roadmap 100% BIO-compliance",
            (
                "Stel per ministerie een roadmap op voor volledige BIO-compliance met "
                "kwartaalmijlpalen."
            ),
            pm("p_berg"),
            "open",
            "hoog",
            date(2026, 4, 30),
        ),
        # --- Architectuur ---
        (
            instr_nora,
            "NORA actualisering cloud-principes",
            (
                "Actualiseer de NORA met nieuwe principes voor cloud-native "
                "architectuur en containerisatie."
            ),
            pm("p_smit"),
            "open",
            "normaal",
            date(2026, 6, 1),
        ),
        # --- NDD ---
        (
            instr_ndd,
            "Businesscase Nederlandse Digitale Dienst",
            (
                "Stel een businesscase op voor de NDD met governance, mandaat, "
                "financiering en fasering."
            ),
            pm("p_dir_ddo"),
            "in_progress",
            "kritiek",
            date(2026, 3, 31),
        ),
        (
            pi_motie_digi_dienst,
            "Reactie op motie versnelling NDD",
            (
                "Stel een kabinetsreactie op de motie Rajkowski op met een versneld "
                "tijdpad voor NDD-oprichting."
            ),
            pm("p_ah_wdo"),
            "open",
            "hoog",
            date(2026, 2, 28),
        ),
        # --- Vendor reductie ---
        (
            maatr_it_inhuur,
            "Nulmeting externe IT-inhuur Rijksdienst",
            (
                "Breng de huidige omvang van externe IT-inhuur per ministerie in kaart "
                "als nulmeting."
            ),
            pm("p_jansen"),
            "in_progress",
            "hoog",
            date(2026, 3, 15),
        ),
        (
            doel_vendor_reductie,
            "Actieplan werving IT-talent Rijksdienst",
            (
                "Ontwikkel een actieplan met concurrerende arbeidsvoorwaarden en "
                "traineeprogramma's voor IT-talent."
            ),
            pm("p_peeters"),
            "open",
            "hoog",
            date(2026, 4, 30),
        ),
        # --- Duurzaamheid ---
        (
            doel_duurzaam_digi,
            "Inventarisatie energieverbruik overheidsdatacenters",
            (
                "Inventariseer het energieverbruik en de PUE-scores van alle "
                "overheidsdatacenters."
            ),
            pm("p_devries"),
            "open",
            "normaal",
            date(2026, 5, 31),
        ),
        # --- Inclusie ---
        (
            doel_inclusie,
            "Monitor digitale zelfredzaamheid 2026",
            (
                "Voer de jaarlijkse monitor digitale zelfredzaamheid uit in "
                "samenwerking met CBS."
            ),
            pm("p_hendriks"),
            "open",
            "normaal",
            date(2026, 6, 30),
        ),
        (
            doel_inclusie,
            "Subsidieregeling digibeten verlengen",
            (
                "Bereid verlenging voor van de subsidieregeling voor bibliotheken en "
                "buurthuizen die digibetencursussen aanbieden."
            ),
            pm("p_hendriks"),
            "open",
            "normaal",
            date(2026, 4, 15),
        ),
        # --- Parlementaire zaken ---
        (
            pi_planningsbrief,
            "Voorbereiden Commissiedebat DiZa feb 2026",
            (
                "Stel de spreekpunten en Q&A op voor het Commissiedebat Digitale Zaken "
                "van februari 2026."
            ),
            pm("p_dir_ds"),
            "in_progress",
            "kritiek",
            date(2026, 2, 14),
        ),
        (
            pi_verzamelbrief_q4,
            "Verzamelbrief Digitalisering Q1 2026 opstellen",
            "Coördineer de bijdragen van alle directies voor de verzamelbrief Q1 2026.",
            pm("p_ah_wdo"),
            "open",
            "hoog",
            date(2026, 3, 31),
        ),
        (
            pi_ek_deskundigen,
            "Voorbereiden deskundigenbijeenkomst EK NDS",
            (
                "Stel briefing en antwoorden op voor de deskundigenbijeenkomst van de "
                "Eerste Kamer over de NDS."
            ),
            pm("p_dgdoo"),
            "open",
            "hoog",
            date(2026, 2, 10),
        ),
        # --- Open Overheid ---
        (
            dos_digi_overheid,
            "Evaluatie Wet open overheid 2025",
            (
                "Coördineer de eerste evaluatie van de Woo en stel een rapportage op "
                "met aanbevelingen."
            ),
            pm("p_dir_open"),
            "in_progress",
            "normaal",
            date(2026, 4, 30),
        ),
        # --- NDS breed ---
        (
            bk_nds,
            "NDS Investeringsagenda opstellen",
            (
                "Stel de investeringsagenda op voor de NDS met prioritering van de 1 "
                "miljard euro jaarlijks budget."
            ),
            pm("p_dgdoo"),
            "open",
            "kritiek",
            date(2026, 6, 30),
        ),
        (
            bk_nds,
            "NDS Voortgangsrapportage H1 2026",
            (
                "Stel de eerste halfjaarlijkse voortgangsrapportage NDS op voor de "
                "Tweede Kamer."
            ),
            pm("p_dir_ds"),
            "open",
            "hoog",
            date(2026, 7, 15),
        ),
        # --- Agent taken ---
        (
            instr_digid,
            "DigiD betrouwbaarheidsniveau-analyse",
            (
                "Analyseer het huidige betrouwbaarheidsniveau van DigiD in relatie tot "
                "eIDAS LoA-eisen en stel een gap-analyse op."
            ),
            agent_identiteit,
            "in_progress",
            "hoog",
            date(2026, 3, 15),
        ),
        (
            instr_eidas_wallet,
            "EUDIW pilotresultaten samenvatten",
            (
                "Verwerk de resultaten van de EUDIW-pilot en stel een beleidsadvies op "
                "over opschaling."
            ),
            agent_identiteit,
            "open",
            "normaal",
            date(2026, 4, 1),
        ),
        (
            bk_wdo,
            "Woo-publicatiepatronen monitoren",
            (
                "Analyseer publicatiefrequentie en categorieën van actieve "
                "Woo-openbaarmaking bij departementen."
            ),
            agent_open,
            "in_progress",
            "normaal",
            date(2026, 3, 31),
        ),
        (
            dos_digi_overheid,
            "Transparantie-benchmark rijksoverheid",
            (
                "Vergelijk transparantiescores van ministeries en stel best practices "
                "samen."
            ),
            agent_open,
            "open",
            "laag",
            date(2026, 5, 15),
        ),
        (
            bk_ai_act,
            "AI Act conformiteitscheck hoog-risico",
            (
                "Beoordeel bestaande hoog-risico AI-systemen op conformiteit met de AI "
                "Act en rapporteer gaps."
            ),
            agent_algo,
            "in_progress",
            "kritiek",
            date(2026, 3, 1),
        ),
        (
            instr_algo_register,
            "Algoritmeregister kwaliteitsaudit",
            (
                "Voer een kwaliteitsaudit uit op registraties in het Algoritmeregister "
                "en stel verbetervoorstellen op."
            ),
            agent_algo,
            "open",
            "hoog",
            date(2026, 4, 15),
        ),
        (
            bk_ibds,
            "Datastrategie-interoperabiliteitstoets",
            (
                "Toets de Interbestuurlijke Datastrategie op alignment met EU Data Act "
                "en Interoperabiliteitsverordening."
            ),
            agent_interop,
            "in_progress",
            "hoog",
            date(2026, 3, 15),
        ),
        (
            instr_nora,
            "NORA-standaarden actualiteitscheck",
            (
                "Analyseer de actualiteit van NORA-standaarden en identificeer "
                "standaarden die herziening vereisen."
            ),
            agent_interop,
            "open",
            "normaal",
            date(2026, 5, 1),
        ),
        (
            instr_bio,
            "BIO-naleving risicoscan departementen",
            (
                "Voer een risicoscan uit op BIO-naleving bij departementen en "
                "prioriteer verbeterpunten."
            ),
            agent_infosec,
            "in_progress",
            "kritiek",
            date(2026, 2, 28),
        ),
        (
            doel_bio_compliance,
            "Dreigingslandschap digitale overheid Q1",
            (
                "Stel een kwartaalrapportage op over het dreigingslandschap voor de "
                "digitale overheid."
            ),
            agent_infosec,
            "open",
            "hoog",
            date(2026, 3, 31),
        ),
        # --- Onverdeelde taken: geen eenheid, geen persoon ---
        (
            dos_digi_overheid,
            "Inventarisatie open standaarden gemeenten",
            (
                "Breng in kaart welke open standaarden momenteel in gebruik zijn bij "
                "gemeenten en welke gaps er bestaan."
            ),
            None,
            "open",
            "hoog",
            date(2026, 3, 15),
        ),
        (
            dos_data,
            "Datalandschap analyse waterschappen",
            (
                "Analyseer het datalandschap van waterschappen en identificeer "
                "mogelijkheden voor data-uitwisseling met het Rijk."
            ),
            None,
            "open",
            "normaal",
            date(2026, 4, 30),
        ),
        (
            dos_ai,
            "EU AI Act gap-analyse rijksoverheid",
            (
                "Voer een gap-analyse uit op de huidige AI-inzet bij de rijksoverheid "
                "ten opzichte van de EU AI Act vereisten."
            ),
            None,
            "open",
            "kritiek",
            date(2026, 2, 28),
        ),
        (
            dos_cio_rijk,
            "Benchmark IT-kosten departementen 2025",
            (
                "Stel een benchmark op van IT-uitgaven per departement over 2025 en "
                "identificeer besparingsmogelijkheden."
            ),
            None,
            "open",
            "normaal",
            date(2026, 5, 31),
        ),
        # --- Onverdeelde taken: wel eenheid, geen persoon ---
        (
            dos_digi_overheid,
            "GDI-componenten migratieplan 2026",
            (
                "Stel een migratieplan op voor de vernieuwing van GDI-componenten "
                "met prioritering en afhankelijkheden."
            ),
            None,
            "open",
            "hoog",
            date(2026, 3, 31),
            dir_ddo,
        ),
        (
            instr_digid,
            "DigiD toegankelijkheidsaudit WCAG 2.2",
            (
                "Voer een toegankelijkheidsaudit uit op DigiD conform WCAG 2.2 "
                "en stel een verbeterplan op."
            ),
            None,
            "open",
            "normaal",
            date(2026, 4, 15),
            afd_id_toegang,
        ),
        (
            dos_ai,
            "Algoritmeregister vulling departement BZK",
            (
                "Zorg ervoor dat alle AI-systemen van BZK correct zijn geregistreerd "
                "in het Algoritmeregister met volledige metadata."
            ),
            None,
            "open",
            "hoog",
            date(2026, 3, 15),
            afd_ai_data,
        ),
        (
            dos_digi_samenleving,
            "Digitale inclusie nulmeting 60+",
            (
                "Voer een nulmeting uit onder 60-plussers over digitale vaardigheden "
                "en toegang tot overheidsdiensten."
            ),
            None,
            "open",
            "normaal",
            date(2026, 5, 1),
            dir_ds,
        ),
        (
            dos_cio_rijk,
            "Cloud-exit strategie kritische systemen",
            (
                "Ontwikkel een cloud-exit strategie voor de meest kritische "
                "overheidssystemen als continuiteitsplan."
            ),
            None,
            "in_progress",
            "kritiek",
            date(2026, 2, 15),
            dir_cio,
        ),
    ]

    subtask_count = 0
    created_tasks: list = []
    for entry in tasks_data:
        node = entry[0]
        title = entry[1]
        description = entry[2]
        assignee = entry[3]
        task_status = entry[4]
        priority = entry[5]
        deadline = entry[6]
        org_eenheid = entry[7] if len(entry) > 7 else None
        subtasks = entry[8] if len(entry) > 8 else []

        parent = await task_repo.create(
            TaskCreate(
                title=title,
                description=description,
                node_id=node.id,
                assignee_id=assignee.id if assignee else None,
                status=task_status,
                priority=priority,
                deadline=deadline,
                organisatie_eenheid_id=(org_eenheid.id if org_eenheid else None),
            )
        )

        for sub in subtasks:
            sub_title, sub_assignee, sub_status, sub_prio, sub_dl = sub
            await task_repo.create(
                TaskCreate(
                    title=sub_title,
                    node_id=node.id,
                    assignee_id=(sub_assignee.id if sub_assignee else None),
                    status=sub_status,
                    priority=sub_prio,
                    deadline=sub_dl,
                    parent_id=parent.id,
                    organisatie_eenheid_id=(org_eenheid.id if org_eenheid else None),
                )
            )
            subtask_count += 1

        created_tasks.append((parent, assignee, node))

    print(f"  Taken: {len(tasks_data)} taken + {subtask_count} subtaken aangemaakt")

    # =========================================================================
    # 7. NODE STAKEHOLDERS
    # =========================================================================
    from bouwmeester.models.node_stakeholder import NodeStakeholder

    stakeholders_data = [
        # Directeuren als eigenaar van koepeldossiers
        (dos_digi_overheid, pm("p_dir_ddo"), "eigenaar"),
        (dos_digi_samenleving, pm("p_dir_ds"), "eigenaar"),
        (dos_cio_rijk, pm("p_dir_cio"), "eigenaar"),
        (dos_ai, pm("p_dir_ds"), "eigenaar"),
        (dos_data, pm("p_ah_ds_d"), "eigenaar"),
        # DigiD / Identiteit
        (maatr_digid_upgrade, pm("p_nguyen"), "betrokken"),
        (maatr_digid_upgrade, pm("p_kaya"), "betrokken"),
        (maatr_digid_upgrade, pm("p_ah_id"), "eigenaar"),
        (instr_digid, pm("p_tl_digid"), "eigenaar"),
        (instr_digid, pm("p_nguyen"), "betrokken"),
        (doel_digid_nieuw, pm("p_ah_id"), "eigenaar"),
        (doel_digid_nieuw, pm("p_kaya"), "adviseur"),
        # EUDIW
        (instr_eidas_wallet, pm("p_tl_eudiw"), "eigenaar"),
        (instr_eidas_wallet, pm("p_kaya"), "betrokken"),
        (doel_eudiw, pm("p_tl_eudiw"), "eigenaar"),
        # WDO
        (bk_wdo, pm("p_ah_wdo"), "eigenaar"),
        (maatr_wdo_transitie, pm("p_ah_wdo"), "eigenaar"),
        (maatr_wdo_transitie, pm("p_achterberg"), "adviseur"),
        # MijnOverheid
        (instr_mijnoverheid, pm("p_tl_mijnov"), "eigenaar"),
        (instr_mijnoverheid, pm("p_visser"), "betrokken"),
        # AI en Algoritmen
        (bk_ai_act, pm("p_dejong"), "eigenaar"),
        (bk_ai_act, pm("p_tl_aiact"), "betrokken"),
        (instr_algo_register, pm("p_bakker"), "eigenaar"),
        (maatr_algo_verpl, pm("p_dejong"), "eigenaar"),
        (bk_algo_kader, pm("p_dejong"), "betrokken"),
        (bk_algo_kader, pm("p_tl_algo"), "eigenaar"),
        (maatr_genai, pm("p_bakker"), "betrokken"),
        (dos_ai, pm("p_dejong"), "betrokken"),
        # Data
        (bk_ibds, pm("p_kumar"), "eigenaar"),
        (doel_fed_data, pm("p_kumar"), "eigenaar"),
        (maatr_data_spaces, pm("p_kumar"), "betrokken"),
        (dos_data, pm("p_tl_data"), "betrokken"),
        # Cloud / CIO
        (bk_cloudbeleid, pm("p_devries"), "eigenaar"),
        (maatr_cloud_exit, pm("p_devries"), "eigenaar"),
        (bk_cio_stelsel, pm("p_dir_cio"), "eigenaar"),
        (bk_cio_stelsel, pm("p_tl_ciostel"), "betrokken"),
        (instr_cio_overleg, pm("p_smit"), "betrokken"),
        (instr_nora, pm("p_smit"), "eigenaar"),
        (maatr_genai, pm("p_devries"), "adviseur"),
        # Informatiebeveiliging
        (instr_bio, pm("p_berg"), "eigenaar"),
        (instr_bio, pm("p_tl_bio"), "betrokken"),
        (doel_bio_compliance, pm("p_berg"), "eigenaar"),
        (doel_bio_compliance, pm("p_timmermans"), "eigenaar"),
        # NDD
        (instr_ndd, pm("p_dir_ddo"), "eigenaar"),
        (instr_ndd, pm("p_ah_wdo"), "betrokken"),
        # Vendor reductie
        (maatr_it_inhuur, pm("p_jansen"), "eigenaar"),
        (doel_vendor_reductie, pm("p_peeters"), "betrokken"),
        (doel_vendor_reductie, pm("p_jansen"), "betrokken"),
        # NDS breed
        (bk_nds, pm("p_dgdoo"), "eigenaar"),
        (bk_nds, pm("p_dir_ddo"), "betrokken"),
        (bk_nds, pm("p_dir_ds"), "betrokken"),
        (bk_nds, pm("p_dir_cio"), "betrokken"),
        # Inclusie
        (doel_inclusie, pm("p_hendriks"), "eigenaar"),
        (doel_inclusie, pm("p_tl_incl"), "betrokken"),
        # Open Overheid
        (dos_digi_overheid, pm("p_dir_open"), "betrokken"),
        # Agent stakeholder koppelingen
        (instr_digid, agent_identiteit, "betrokken"),
        (instr_eidas_wallet, agent_identiteit, "betrokken"),
        (doel_digid_nieuw, agent_identiteit, "betrokken"),
        (maatr_digid_upgrade, agent_identiteit, "adviseur"),
        (dos_digi_overheid, agent_open, "betrokken"),
        (bk_wdo, agent_open, "betrokken"),
        (bk_ai_act, agent_algo, "betrokken"),
        (bk_algo_kader, agent_algo, "betrokken"),
        (instr_algo_register, agent_algo, "betrokken"),
        (maatr_algo_verpl, agent_algo, "adviseur"),
        (maatr_genai, agent_algo, "adviseur"),
        (bk_ibds, agent_interop, "betrokken"),
        (instr_nora, agent_interop, "betrokken"),
        (instr_ndd, agent_interop, "adviseur"),
        (doel_fed_data, agent_interop, "betrokken"),
        (instr_bio, agent_infosec, "betrokken"),
        (doel_bio_compliance, agent_infosec, "eigenaar"),
        (bk_cloudbeleid, agent_infosec, "adviseur"),
    ]

    for node, person, rol in stakeholders_data:
        db.add(
            NodeStakeholder(
                node_id=node.id,
                person_id=person.id,
                rol=rol,
            )
        )
    await db.flush()

    print(f"  Stakeholders: {len(stakeholders_data)} koppelingen aangemaakt")

    # =========================================================================
    # 8. TAGS — Hierarchical policy domain tags
    # =========================================================================

    # Root tags
    tag_digitalisering = await tag_repo.create(TagCreate(name="digitalisering"))
    tag_overheid = await tag_repo.create(TagCreate(name="overheid"))
    tag_veiligheid = await tag_repo.create(TagCreate(name="veiligheid"))
    tag_wetgeving = await tag_repo.create(TagCreate(name="wetgeving"))
    tag_eu = await tag_repo.create(TagCreate(name="europees"))
    tag_data = await tag_repo.create(TagCreate(name="data"))
    tag_inclusie = await tag_repo.create(TagCreate(name="inclusie"))
    tag_duurzaamheid = await tag_repo.create(TagCreate(name="duurzaamheid"))

    # Digitalisering subtags
    tag_ai = await tag_repo.create(
        TagCreate(name="digitalisering/AI", parent_id=tag_digitalisering.id)
    )
    tag_algoritmen = await tag_repo.create(
        TagCreate(name="digitalisering/algoritmen", parent_id=tag_digitalisering.id)
    )
    tag_cloud = await tag_repo.create(
        TagCreate(name="digitalisering/cloud", parent_id=tag_digitalisering.id)
    )
    tag_ident = await tag_repo.create(
        TagCreate(name="digitalisering/identiteit", parent_id=tag_digitalisering.id)
    )
    tag_infra = await tag_repo.create(
        TagCreate(name="digitalisering/infrastructuur", parent_id=tag_digitalisering.id)
    )
    tag_genai = await tag_repo.create(
        TagCreate(name="digitalisering/AI/generatieve-AI", parent_id=tag_ai.id)
    )
    tag_opensource = await tag_repo.create(
        TagCreate(name="digitalisering/open-source", parent_id=tag_digitalisering.id)
    )

    # Overheid subtags — more specific than just "overheid/dienstverlening"
    tag_dienstverlening_digitaal = await tag_repo.create(
        TagCreate(name="overheid/digitale-dienstverlening", parent_id=tag_overheid.id)
    )
    await tag_repo.create(
        TagCreate(name="overheid/fysieke-dienstverlening", parent_id=tag_overheid.id)
    )
    tag_cio = await tag_repo.create(
        TagCreate(name="overheid/CIO-stelsel", parent_id=tag_overheid.id)
    )
    tag_architectuur = await tag_repo.create(
        TagCreate(name="overheid/architectuur", parent_id=tag_overheid.id)
    )
    tag_it_personeel = await tag_repo.create(
        TagCreate(name="overheid/IT-personeel", parent_id=tag_overheid.id)
    )
    tag_rijksbrede_ict = await tag_repo.create(
        TagCreate(name="overheid/rijksbrede-ICT", parent_id=tag_overheid.id)
    )

    # Veiligheid subtags
    tag_cyber = await tag_repo.create(
        TagCreate(name="veiligheid/cybersecurity", parent_id=tag_veiligheid.id)
    )
    tag_privacy = await tag_repo.create(
        TagCreate(name="veiligheid/privacy", parent_id=tag_veiligheid.id)
    )
    tag_bio = await tag_repo.create(
        TagCreate(name="veiligheid/BIO", parent_id=tag_veiligheid.id)
    )

    # Wetgeving subtags
    tag_wdo = await tag_repo.create(
        TagCreate(name="wetgeving/WDO", parent_id=tag_wetgeving.id)
    )
    tag_ai_act = await tag_repo.create(
        TagCreate(name="wetgeving/AI-Act", parent_id=tag_wetgeving.id)
    )
    await tag_repo.create(TagCreate(name="wetgeving/Woo", parent_id=tag_wetgeving.id))

    # EU subtags
    tag_eidas = await tag_repo.create(
        TagCreate(name="europees/eIDAS", parent_id=tag_eu.id)
    )
    tag_eudiw = await tag_repo.create(
        TagCreate(name="europees/EUDIW", parent_id=tag_eu.id)
    )
    tag_eu_data_governance = await tag_repo.create(
        TagCreate(name="europees/Data-Governance-Act", parent_id=tag_eu.id)
    )

    # Data subtags — more specific
    tag_federatief = await tag_repo.create(
        TagCreate(name="data/federatief-datastelsel", parent_id=tag_data.id)
    )
    tag_data_spaces = await tag_repo.create(
        TagCreate(name="data/data-spaces", parent_id=tag_data.id)
    )
    tag_open_data = await tag_repo.create(
        TagCreate(name="data/open-data", parent_id=tag_data.id)
    )
    tag_data_kwaliteit = await tag_repo.create(
        TagCreate(name="data/datakwaliteit", parent_id=tag_data.id)
    )

    # Inclusie subtags
    tag_digitale_kloof = await tag_repo.create(
        TagCreate(name="inclusie/digitale-kloof", parent_id=tag_inclusie.id)
    )
    tag_toegankelijkheid = await tag_repo.create(
        TagCreate(name="inclusie/toegankelijkheid", parent_id=tag_inclusie.id)
    )

    print("  Tags: 40+ tags aangemaakt")

    # =========================================================================
    # 9. NODE-TAG ASSOCIATIONS
    # =========================================================================

    node_tag_data = [
        # Dossiers
        (dos_digi_overheid, [tag_dienstverlening_digitaal, tag_rijksbrede_ict]),
        (dos_digi_samenleving, [tag_digitale_kloof, tag_toegankelijkheid]),
        (dos_cio_rijk, [tag_cio, tag_cloud, tag_rijksbrede_ict]),
        (dos_ai, [tag_ai, tag_algoritmen]),
        (dos_data, [tag_federatief, tag_data_kwaliteit]),
        # Beleidskaders
        (bk_nds, [tag_rijksbrede_ict, tag_dienstverlening_digitaal]),
        (bk_ibds, [tag_federatief, tag_data_kwaliteit]),
        (bk_wdo, [tag_wdo, tag_dienstverlening_digitaal]),
        (bk_ai_act, [tag_ai_act, tag_ai, tag_eu]),
        (bk_cio_stelsel, [tag_cio, tag_rijksbrede_ict]),
        (bk_cloudbeleid, [tag_cloud, tag_cyber]),
        (bk_algo_kader, [tag_algoritmen, tag_ai]),
        # Doelen
        (doel_digid_nieuw, [tag_ident, tag_dienstverlening_digitaal]),
        (doel_algo_register, [tag_algoritmen, tag_ai]),
        (doel_eudiw, [tag_eudiw, tag_eidas, tag_ident]),
        (doel_fed_data, [tag_federatief, tag_data_kwaliteit]),
        (doel_vendor_reductie, [tag_cloud, tag_opensource]),
        (doel_duurzaam_digi, [tag_duurzaamheid, tag_infra]),
        (doel_bio_compliance, [tag_bio, tag_cyber]),
        (doel_inclusie, [tag_digitale_kloof, tag_toegankelijkheid]),
        # Instrumenten
        (instr_digid, [tag_ident, tag_dienstverlening_digitaal, tag_infra]),
        (instr_mijnoverheid, [tag_dienstverlening_digitaal, tag_infra]),
        (instr_algo_register, [tag_algoritmen, tag_ai]),
        (instr_nora, [tag_architectuur, tag_rijksbrede_ict]),
        (instr_ndd, [tag_rijksbrede_ict, tag_infra]),
        (instr_bio, [tag_bio, tag_cyber]),
        (instr_eidas_wallet, [tag_eudiw, tag_eidas, tag_ident]),
        (instr_cio_overleg, [tag_cio, tag_rijksbrede_ict]),
        # Maatregelen
        (maatr_algo_verpl, [tag_algoritmen, tag_ai_act]),
        (maatr_cloud_exit, [tag_cloud, tag_opensource]),
        (maatr_digid_upgrade, [tag_ident, tag_infra]),
        (maatr_it_inhuur, [tag_it_personeel]),
        (maatr_wdo_transitie, [tag_wdo, tag_dienstverlening_digitaal]),
        (maatr_genai, [tag_genai, tag_ai]),
        (maatr_data_spaces, [tag_data_spaces, tag_eu_data_governance]),
        # Politieke inputs
        (pi_motie_sixdijkstra, [tag_genai, tag_opensource]),
        (pi_motie_veldhoen, [tag_algoritmen, tag_ai_act]),
        (pi_kamervraag_digid, [tag_ident, tag_dienstverlening_digitaal]),
        (pi_kamervraag_cloud, [tag_cloud]),
        (pi_motie_digi_dienst, [tag_rijksbrede_ict, tag_infra]),
        # Problemen
        (prob_digitale_kloof, [tag_digitale_kloof, tag_toegankelijkheid]),
        (prob_vendor_lock, [tag_cloud, tag_opensource]),
        (prob_algo_bias, [tag_algoritmen, tag_privacy]),
        (prob_data_silo, [tag_federatief, tag_data_kwaliteit]),
        (prob_cyber_dreiging, [tag_cyber]),
        # Effecten
        (
            eff_digid_bereik,
            [tag_ident, tag_dienstverlening_digitaal, tag_digitale_kloof],
        ),
        (eff_algo_transparant, [tag_algoritmen, tag_ai]),
        (eff_data_beschikbaar, [tag_open_data, tag_federatief]),
        (eff_minder_inhuur, [tag_it_personeel]),
    ]

    count = 0
    for node, tags in node_tag_data:
        for tag in tags:
            await tag_repo.add_tag_to_node(node.id, tag.id)
            count += 1

    print(f"  Node-tag koppelingen: {count} koppelingen aangemaakt")

    # =========================================================================
    # 9. MOTIE IMPORTS — Seeded imports with review tasks
    # =========================================================================

    from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge

    # Motie 1: routed to afd_ai_data (eigenaar of matched nodes is in that unit)
    mi_node_1 = await node_repo.create(
        CorpusNodeCreate(
            title="Motie Kathmann (GL-PvdA) — Transparantie algoritmegebruik gemeenten",
            node_type="politieke_input",
            description=(
                "Aangenomen motie die de regering verzoekt gemeenten te verplichten "
                "hun algoritmegebruik te registreren in het Algoritmeregister en "
                "jaarlijks een transparantierapportage te publiceren."
            ),
            status="actief",
        )
    )
    from bouwmeester.models.politieke_input import PolitiekeInput as PIModel

    db.add(
        PIModel(
            id=mi_node_1.id,
            type="motie",
            referentie="36560-45",
            datum=date(2026, 1, 21),
            status="aangenomen",
        )
    )
    await db.flush()

    # Tag the node
    for tag in [tag_algoritmen, tag_ai]:
        await tag_repo.add_tag_to_node(mi_node_1.id, tag.id)

    mi_1 = ParlementairItem(
        zaak_id="mi-seed-kathmann-algoritmen",
        zaak_nummer="36560-45",
        titel=(
            "Motie van het lid Kathmann over transparantie algoritmegebruik gemeenten"
        ),
        onderwerp="Transparantie algoritmegebruik gemeenten",
        bron="tweede_kamer",
        datum=date(2026, 1, 21),
        status="imported",
        corpus_node_id=mi_node_1.id,
        indieners=["Kathmann"],
        llm_samenvatting=(
            "Motie verzoekt de regering gemeenten te verplichten algoritmegebruik "
            "te registreren in het Algoritmeregister."
        ),
        matched_tags=["algoritmen", "ai"],
        imported_at=datetime.now(UTC) - timedelta(days=3),
    )
    db.add(mi_1)
    await db.flush()

    # Suggested edges for motie 1
    db.add(
        SuggestedEdge(
            parlementair_item_id=mi_1.id,
            target_node_id=instr_algo_register.id,
            edge_type_id="adresseert",
            confidence=0.9,
            reason="Gedeelde tags: algoritmen, ai",
            status="pending",
        )
    )
    db.add(
        SuggestedEdge(
            parlementair_item_id=mi_1.id,
            target_node_id=bk_algo_kader.id,
            edge_type_id="adresseert",
            confidence=0.8,
            reason="Gedeelde tags: algoritmen",
            status="pending",
        )
    )
    await db.flush()

    # Review task for motie 1 — routed to afd_ai_data (eigenaar of algo register)
    await task_repo.create(
        TaskCreate(
            title="Beoordeel motie: Transparantie algoritmegebruik gemeenten",
            description=(
                "Zaak: 36560-45\n"
                "Bron: tweede_kamer\n\n"
                "Motie verzoekt de regering gemeenten te verplichten algoritmegebruik "
                "te registreren in het Algoritmeregister.\n\n"
                "2 gerelateerde beleidsdossiers gevonden."
            ),
            node_id=mi_node_1.id,
            priority="hoog",
            status="open",
            deadline=date(2026, 2, 4),
            organisatie_eenheid_id=afd_ai_data.id,
            assignee_id=None,
            parlementair_item_id=mi_1.id,
        )
    )

    # Motie 2: routed to afd_id_toegang (eigenaar of DigiD nodes)
    mi_node_2 = await node_repo.create(
        CorpusNodeCreate(
            title="Motie Dekker-Abdulaziz (D66) — DigiD voor EU-burgers",
            node_type="politieke_input",
            description=(
                "Motie die de regering verzoekt DigiD beschikbaar te maken voor "
                "EU-burgers die in Nederland wonen maar geen BSN hebben, via "
                "koppeling met het eIDAS-stelsel."
            ),
            status="actief",
        )
    )
    db.add(
        PIModel(
            id=mi_node_2.id,
            type="motie",
            referentie="36560-52",
            datum=date(2026, 1, 28),
            status="aangenomen",
        )
    )
    await db.flush()

    for tag in [tag_ident, tag_eidas]:
        await tag_repo.add_tag_to_node(mi_node_2.id, tag.id)

    mi_2 = ParlementairItem(
        zaak_id="mi-seed-dekker-digid-eu",
        zaak_nummer="36560-52",
        titel="Motie van het lid Dekker-Abdulaziz over DigiD voor EU-burgers",
        onderwerp="DigiD voor EU-burgers",
        bron="tweede_kamer",
        datum=date(2026, 1, 28),
        status="imported",
        corpus_node_id=mi_node_2.id,
        indieners=["Dekker-Abdulaziz"],
        llm_samenvatting=(
            "Motie verzoekt DigiD beschikbaar te maken voor EU-burgers zonder BSN "
            "via eIDAS-koppeling."
        ),
        matched_tags=["digitale identiteit", "eIDAS"],
        imported_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(mi_2)
    await db.flush()

    db.add(
        SuggestedEdge(
            parlementair_item_id=mi_2.id,
            target_node_id=instr_digid.id,
            edge_type_id="adresseert",
            confidence=0.85,
            reason="Gedeelde tags: digitale identiteit",
            status="pending",
        )
    )
    db.add(
        SuggestedEdge(
            parlementair_item_id=mi_2.id,
            target_node_id=instr_eidas_wallet.id,
            edge_type_id="adresseert",
            confidence=0.75,
            reason="Gedeelde tags: eIDAS",
            status="pending",
        )
    )
    await db.flush()

    # Review task for motie 2 — routed to afd_id_toegang
    await task_repo.create(
        TaskCreate(
            title="Beoordeel motie: DigiD voor EU-burgers",
            description=(
                "Zaak: 36560-52\n"
                "Bron: tweede_kamer\n\n"
                "Motie verzoekt DigiD beschikbaar te maken voor EU-burgers zonder BSN "
                "via eIDAS-koppeling.\n\n"
                "2 gerelateerde beleidsdossiers gevonden."
            ),
            node_id=mi_node_2.id,
            priority="hoog",
            status="open",
            deadline=date(2026, 2, 11),
            organisatie_eenheid_id=afd_id_toegang.id,
            assignee_id=None,
            parlementair_item_id=mi_2.id,
        )
    )

    # Motie 3: NO unit routing (no matching eigenaar stakeholders) → "Geen eenheid"
    mi_node_3 = await node_repo.create(
        CorpusNodeCreate(
            title=(
                "Motie Van Baarle (DENK) — Digitale dienstverlening in meerdere talen"
            ),
            node_type="politieke_input",
            description=(
                "Motie die de regering verzoekt de belangrijkste digitale "
                "overheidsdiensten (DigiD, MijnOverheid, Overheid.nl) ook in het "
                "Engels, Turks en Arabisch beschikbaar te maken."
            ),
            status="actief",
        )
    )
    db.add(
        PIModel(
            id=mi_node_3.id,
            type="motie",
            referentie="36560-61",
            datum=date(2026, 2, 3),
            status="aangenomen",
        )
    )
    await db.flush()

    for tag in [tag_toegankelijkheid, tag_digitale_kloof]:
        await tag_repo.add_tag_to_node(mi_node_3.id, tag.id)

    mi_3 = ParlementairItem(
        zaak_id="mi-seed-vanbaarle-meertalig",
        zaak_nummer="36560-61",
        titel=(
            "Motie van het lid Van Baarle over digitale dienstverlening "
            "in meerdere talen"
        ),
        onderwerp="Digitale dienstverlening in meerdere talen",
        bron="tweede_kamer",
        datum=date(2026, 2, 3),
        status="imported",
        corpus_node_id=mi_node_3.id,
        indieners=["Van Baarle"],
        llm_samenvatting=(
            "Motie verzoekt overheidsdiensten meertalig beschikbaar te maken "
            "voor burgers die het Nederlands onvoldoende beheersen."
        ),
        matched_tags=["toegankelijkheid", "digitale kloof"],
        imported_at=datetime.now(UTC),
    )
    db.add(mi_3)
    await db.flush()

    # No suggested edges with clear eigenaar → lands in "Geen eenheid"
    db.add(
        SuggestedEdge(
            parlementair_item_id=mi_3.id,
            target_node_id=prob_digitale_kloof.id,
            edge_type_id="adresseert",
            confidence=0.7,
            reason="Gedeelde tags: digitale kloof, toegankelijkheid",
            status="pending",
        )
    )
    await db.flush()

    # Review task for motie 3 — NO unit (will appear in "Geen eenheid")
    await task_repo.create(
        TaskCreate(
            title="Beoordeel motie: Digitale dienstverlening in meerdere talen",
            description=(
                "Zaak: 36560-61\n"
                "Bron: tweede_kamer\n\n"
                "Motie verzoekt overheidsdiensten meertalig beschikbaar te maken "
                "voor burgers die het Nederlands onvoldoende beheersen.\n\n"
                "1 gerelateerd beleidsdossier gevonden."
            ),
            node_id=mi_node_3.id,
            priority="hoog",
            status="open",
            deadline=date(2026, 2, 17),
            organisatie_eenheid_id=None,
            assignee_id=None,
            parlementair_item_id=mi_3.id,
        )
    )

    print("  Motie imports: 3 moties met review-taken aangemaakt")

    # =========================================================================
    # 10. NOTIFICATIONS
    # =========================================================================
    from bouwmeester.models.notification import Notification

    now = datetime.now(UTC)
    notifications = []

    # Find a few assigned tasks for notification references
    assigned_tasks = [(t, a, n) for t, a, n in created_tasks if a is not None]

    # --- task_assigned: new tasks assigned to people ---
    if len(assigned_tasks) >= 3:
        t, a, n = assigned_tasks[0]
        notifications.append(
            Notification(
                person_id=a.id,
                type="task_assigned",
                title=f"Taak toegewezen: {t.title}",
                message=f"De taak '{t.title}' op '{n.title}' is aan jou toegewezen.",
                is_read=False,
                related_task_id=t.id,
                related_node_id=n.id,
                sender_id=pm("p_dir_ddo").id,
                created_at=now - timedelta(hours=2),
            )
        )
        t2, a2, n2 = assigned_tasks[1]
        notifications.append(
            Notification(
                person_id=a2.id,
                type="task_assigned",
                title=f"Taak toegewezen: {t2.title}",
                message=f"De taak '{t2.title}' op '{n2.title}' is aan jou toegewezen.",
                is_read=True,
                related_task_id=t2.id,
                related_node_id=n2.id,
                sender_id=pm("p_dir_ds").id,
                created_at=now - timedelta(days=1),
            )
        )
        t3, a3, n3 = assigned_tasks[2]
        notifications.append(
            Notification(
                person_id=a3.id,
                type="task_assigned",
                title=f"Taak toegewezen: {t3.title}",
                message=(
                    f"De taak '{t3.title}' is aan jou "
                    f"toegewezen door {pm('p_dir_cio').naam}."
                ),
                is_read=False,
                related_task_id=t3.id,
                related_node_id=n3.id,
                sender_id=pm("p_dir_cio").id,
                created_at=now - timedelta(hours=6),
            )
        )

    # --- task_completed: completed task notifications ---
    done_tasks = [(t, a, n) for t, a, n in created_tasks if t.status == "done" and a]
    if done_tasks:
        t, a, n = done_tasks[0]
        # Notify stakeholders of the node
        notifications.append(
            Notification(
                person_id=pm("p_dir_ddo").id,
                type="task_completed",
                title=f"Taak afgerond: {t.title}",
                message=f"{a.naam} heeft de taak '{t.title}' afgerond.",
                is_read=False,
                related_task_id=t.id,
                related_node_id=n.id,
                sender_id=a.id,
                created_at=now - timedelta(hours=4),
            )
        )

    # --- task_reassigned: someone was reassigned ---
    if pm("p_nguyen") and pm("p_kaya") and len(assigned_tasks) >= 4:
        t4, _, n4 = assigned_tasks[3]
        notifications.append(
            Notification(
                person_id=pm("p_nguyen").id,
                type="task_reassigned",
                title=f"Taak overgedragen: {t4.title}",
                message=(
                    f"De taak '{t4.title}' is overgedragen aan {pm('p_kaya').naam}. "
                    "Je bent niet langer verantwoordelijk."
                ),
                is_read=False,
                related_task_id=t4.id,
                related_node_id=n4.id,
                created_at=now - timedelta(hours=3),
            )
        )
        notifications.append(
            Notification(
                person_id=pm("p_kaya").id,
                type="task_assigned",
                title=f"Taak toegewezen: {t4.title}",
                message=(
                    f"De taak '{t4.title}' is aan jou overgedragen "
                    f"(voorheen: {pm('p_nguyen').naam})."
                ),
                is_read=False,
                related_task_id=t4.id,
                related_node_id=n4.id,
                created_at=now - timedelta(hours=3),
            )
        )

    # --- node_updated: corpus node was edited ---
    if pm("p_dejong"):
        notifications.append(
            Notification(
                person_id=pm("p_dir_ddo").id,
                type="node_updated",
                title=f"Node bijgewerkt: {dos_digi_overheid.title}",
                message=(
                    f"{pm('p_dejong').naam} heeft "
                    f"'{dos_digi_overheid.title}' bijgewerkt."
                ),
                is_read=True,
                related_node_id=dos_digi_overheid.id,
                sender_id=pm("p_dejong").id,
                created_at=now - timedelta(days=2),
            )
        )
    notifications.append(
        Notification(
            person_id=pm("p_dir_ds").id,
            type="node_updated",
            title=f"Node bijgewerkt: {dos_ai.title}",
            message=f"{pm('p_dir_ddo').naam} heeft '{dos_ai.title}' bijgewerkt.",
            is_read=False,
            related_node_id=dos_ai.id,
            sender_id=pm("p_dir_ddo").id,
            created_at=now - timedelta(hours=5),
        )
    )

    # --- edge_created: new edges between nodes ---
    if pm("p_devries"):
        notifications.append(
            Notification(
                person_id=pm("p_devries").id,
                type="edge_created",
                title="Nieuwe relatie aangemaakt",
                message=(
                    f"Er is een relatie gelegd tussen "
                    f"'{dos_digi_overheid.title}' en '{bk_nds.title}'."
                ),
                is_read=False,
                related_node_id=dos_digi_overheid.id,
                created_at=now - timedelta(hours=8),
            )
        )
    notifications.append(
        Notification(
            person_id=pm("p_dir_ddo").id,
            type="edge_created",
            title="Nieuwe relatie aangemaakt",
            message=(
                f"Er is een relatie gelegd tussen "
                f"'{dos_ai.title}' en '{bk_algo_kader.title}'."
            ),
            is_read=True,
            related_node_id=dos_ai.id,
            created_at=now - timedelta(days=3),
        )
    )

    # --- stakeholder_added: person added as stakeholder ---
    if pm("p_kumar"):
        notifications.append(
            Notification(
                person_id=pm("p_kumar").id,
                type="stakeholder_added",
                title=f"Toegevoegd als betrokkene: {dos_data.title}",
                message=(
                    f"Je bent toegevoegd als betrokkene aan '{dos_data.title}' "
                    f"door {pm('p_dir_ds').naam}."
                ),
                is_read=False,
                related_node_id=dos_data.id,
                sender_id=pm("p_dir_ds").id,
                created_at=now - timedelta(hours=1),
            )
        )
    if pm("p_nguyen"):
        notifications.append(
            Notification(
                person_id=pm("p_nguyen").id,
                type="stakeholder_added",
                title=f"Toegevoegd als adviseur: {dos_digi_overheid.title}",
                message=(
                    f"Je bent toegevoegd als adviseur aan '{dos_digi_overheid.title}'."
                ),
                is_read=True,
                related_node_id=dos_digi_overheid.id,
                sender_id=pm("p_dir_ddo").id,
                created_at=now - timedelta(days=1, hours=4),
            )
        )

    # --- stakeholder_role_changed ---
    if pm("p_dejong"):
        notifications.append(
            Notification(
                person_id=pm("p_dejong").id,
                type="stakeholder_role_changed",
                title=f"Rol gewijzigd: {dos_digi_overheid.title}",
                message=(
                    f"Je rol op '{dos_digi_overheid.title}' is "
                    "gewijzigd van betrokkene naar eigenaar."
                ),
                is_read=False,
                related_node_id=dos_digi_overheid.id,
                created_at=now - timedelta(hours=12),
            )
        )

    # --- mention: @mentions in descriptions ---
    if pm("p_kaya"):
        notifications.append(
            Notification(
                person_id=pm("p_kaya").id,
                type="mention",
                title="Genoemd in een beschrijving",
                message=(
                    f"Je bent genoemd in de beschrijving van '{dos_ai.title}' "
                    f"door {pm('p_dir_ds').naam}."
                ),
                is_read=False,
                related_node_id=dos_ai.id,
                sender_id=pm("p_dir_ds").id,
                created_at=now - timedelta(hours=7),
            )
        )

    # --- direct_message: dual-root threads ---
    # Thread 1: p_dir_cio → p_dir_ddo
    dm1_msg = (
        "Hi, kunnen we morgen overleggen over de cloud-exit strategie? "
        "Er zijn nieuwe inzichten vanuit het CIO-overleg."
    )
    # Recipient root (unread)
    dm1_recipient_root = Notification(
        person_id=pm("p_dir_ddo").id,
        type="direct_message",
        title="Bericht van " + pm("p_dir_cio").naam,
        message=dm1_msg,
        is_read=False,
        sender_id=pm("p_dir_cio").id,
        created_at=now - timedelta(hours=3),
    )
    db.add(dm1_recipient_root)
    await db.flush()
    dm1_recipient_root.thread_id = dm1_recipient_root.id
    await db.flush()

    # Sender root (unread because recipient replied)
    dm1_sender_root = Notification(
        person_id=pm("p_dir_cio").id,
        type="direct_message",
        title="Bericht aan " + pm("p_dir_ddo").naam,
        message=dm1_msg,
        is_read=False,
        sender_id=pm("p_dir_cio").id,
        thread_id=dm1_recipient_root.id,
        created_at=now - timedelta(hours=3),
    )
    db.add(dm1_sender_root)
    await db.flush()

    # Reply (parented to thread_id)
    dm1_reply = Notification(
        person_id=pm("p_dir_cio").id,
        type="direct_message",
        title="Reactie van " + pm("p_dir_ddo").naam,
        message="Goed idee, ik plan een afspraak in voor morgenochtend.",
        is_read=False,
        sender_id=pm("p_dir_ddo").id,
        parent_id=dm1_recipient_root.id,
        created_at=now - timedelta(hours=2, minutes=45),
    )
    notifications.append(dm1_reply)

    # Thread 2: p_dir_ddo → p_nguyen
    if pm("p_nguyen"):
        dm2_msg = (
            "Kun je de impact-analyse voor de NL Design System migratie "
            "volgende week afronden?"
        )
        # Recipient root (unread)
        dm2_recipient_root = Notification(
            person_id=pm("p_nguyen").id,
            type="direct_message",
            title="Bericht van " + pm("p_dir_ddo").naam,
            message=dm2_msg,
            is_read=False,
            sender_id=pm("p_dir_ddo").id,
            created_at=now - timedelta(hours=5),
        )
        db.add(dm2_recipient_root)
        await db.flush()
        dm2_recipient_root.thread_id = dm2_recipient_root.id
        await db.flush()

        # Sender root (Mark — unread because Linh replied)
        dm2_sender_root = Notification(
            person_id=pm("p_dir_ddo").id,
            type="direct_message",
            title="Bericht aan " + pm("p_nguyen").naam,
            message=dm2_msg,
            is_read=False,
            sender_id=pm("p_dir_ddo").id,
            thread_id=dm2_recipient_root.id,
            created_at=now - timedelta(hours=5),
        )
        db.add(dm2_sender_root)
        await db.flush()

        # Reply from Linh (parented to thread_id)
        notifications.append(
            Notification(
                person_id=pm("p_dir_ddo").id,
                type="direct_message",
                title="Reactie van " + pm("p_nguyen").naam,
                message="Ik ga ermee aan de slag, deadline halen we.",
                is_read=False,
                sender_id=pm("p_nguyen").id,
                parent_id=dm2_recipient_root.id,
                created_at=now - timedelta(hours=4, minutes=30),
            )
        )

    # --- politieke_input_imported ---
    notifications.append(
        Notification(
            person_id=pm("p_dir_ds").id,
            type="politieke_input_imported",
            title="Nieuwe motie geïmporteerd",
            message=(
                "Motie 'Versterking digitale autonomie van de overheid' is "
                "automatisch geïmporteerd uit de Tweede Kamer API."
            ),
            is_read=False,
            related_node_id=mi_node_1.id,
            created_at=now - timedelta(hours=1, minutes=30),
        )
    )
    notifications.append(
        Notification(
            person_id=pm("p_dir_ddo").id,
            type="politieke_input_imported",
            title="Nieuwe motie geïmporteerd",
            message=(
                "Motie 'Digitale dienstverlening in meerdere talen' is "
                "automatisch geïmporteerd."
            ),
            is_read=True,
            related_node_id=mi_node_3.id,
            created_at=now - timedelta(days=2, hours=6),
        )
    )

    for n in notifications:
        db.add(n)
    await db.flush()

    notif_count = len(notifications) + 1  # +1 for dm_parent added separately
    if pm("p_nguyen"):
        notif_count += 1  # dm2_parent
    print(f"  Notificaties: {notif_count} notificaties aangemaakt")

    await db.commit()
    print("\nSeed voltooid!")


async def main() -> None:
    async with async_session() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
