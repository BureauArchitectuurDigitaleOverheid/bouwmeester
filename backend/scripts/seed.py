"""Seed script: realistic BZK/DGDOO Digitale Overheid dataset.

Run with: cd backend && uv run python scripts/seed.py
Clears all existing data and populates organisatie, personen, corpus, edges, and tasks.
"""

import asyncio
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.repositories.corpus_node import CorpusNodeRepository
from bouwmeester.repositories.edge import EdgeRepository
from bouwmeester.repositories.edge_type import EdgeTypeRepository
from bouwmeester.repositories.organisatie_eenheid import OrganisatieEenheidRepository
from bouwmeester.repositories.person import PersonRepository
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.corpus_node import CorpusNodeCreate
from bouwmeester.schema.edge import EdgeCreate
from bouwmeester.schema.edge_type import EdgeTypeCreate
from bouwmeester.schema.organisatie_eenheid import OrganisatieEenheidCreate
from bouwmeester.schema.person import PersonCreate
from bouwmeester.schema.tag import TagCreate
from bouwmeester.schema.task import TaskCreate


async def seed(db: AsyncSession) -> None:
    # Clear existing data (order matters due to FKs)
    for table in [
        "suggested_edge",
        "motie_import",
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
        "corpus_node",
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
            naam="Directie Digitale Overheid",
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
            naam="Afdeling Basisinfrastructuur en Dienstverlening",
            type="afdeling",
            parent_id=dir_ddo.id,
            beschrijving=(
                "Beleid voor digitale basisregistraties, MijnOverheid, machtigen en "
                "Generieke Digitale Infrastructuur (GDI)."
            ),
        )
    )
    afd_id_toegang = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Afdeling Identiteit en Toegang",
            type="afdeling",
            parent_id=dir_ddo.id,
            beschrijving=(
                "DigiD, eIDAS, Europese digitale identiteit (EUDIW), elektronische "
                "handtekeningen en inlogmiddelen."
            ),
        )
    )
    afd_wdo = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Afdeling Wet- en Regelgeving Digitale Overheid",
            type="afdeling",
            parent_id=dir_ddo.id,
            beschrijving=(
                "Juridische kaders: Wet Digitale Overheid, Interoperabiliteitswet, "
                "stelselwetgeving."
            ),
        )
    )
    team_digid = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team DigiD Beleid",
            type="team",
            parent_id=afd_id_toegang.id,
            beschrijving="Beleidsregie op DigiD als publieke authenticatievoorziening.",
        )
    )
    team_eudiw = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team EUDIW",
            type="team",
            parent_id=afd_id_toegang.id,
            beschrijving=(
                "Europese Digitale Identiteit Wallet — Nederlandse implementatie en "
                "pilotprogramma."
            ),
        )
    )
    team_mijnoverheid = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team MijnOverheid",
            type="team",
            parent_id=afd_basisinfra.id,
            beschrijving="Doorontwikkeling en beheer van het MijnOverheid-portaal.",
        )
    )
    team_gdi = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team GDI en Standaarden",
            type="team",
            parent_id=afd_basisinfra.id,
            beschrijving=(
                "Generieke Digitale Infrastructuur, standaarden en interoperabiliteit."
            ),
        )
    )

    # --- Directie Digitale Samenleving (~50 FTE) ---
    dir_ds = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Directie Digitale Samenleving",
            type="directie",
            parent_id=dgdoo.id,
            beschrijving=(
                "Beleid voor algoritmes, AI, data-ethiek, online veiligheid, digitale "
                "inclusie en de verhouding burger-technologie."
            ),
        )
    )

    afd_ai_data = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Afdeling AI, Algoritmen, Data en Digitale Inclusie",
            type="afdeling",
            parent_id=dir_ds.id,
            beschrijving=(
                "Algoritmeregister, AI-verordening implementatie,"
                " algoritmekader, IBDS, data-ethiek en digitale inclusie."
            ),
        )
    )
    afd_strat_intl = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Afdeling Strategie, Internationaal en Communicatie",
            type="afdeling",
            parent_id=dir_ds.id,
            beschrijving=(
                "NDS-coördinatie, internationale digitaliseringsdossiers, EU-raden en "
                "communicatie."
            ),
        )
    )
    team_algo = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team Algoritmeregister",
            type="team",
            parent_id=afd_ai_data.id,
            beschrijving=(
                "Beheer en doorontwikkeling van het overheidsbreed Algoritmeregister."
            ),
        )
    )
    team_ai_act = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team AI Act Implementatie",
            type="team",
            parent_id=afd_ai_data.id,
            beschrijving=(
                "Implementatie EU AI-verordening, algoritmekader en toezichtsketen."
            ),
        )
    )
    team_data = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team Data en IBDS",
            type="team",
            parent_id=afd_ai_data.id,
            beschrijving=(
                "Interbestuurlijke Datastrategie, Federatief Datastelsel en open data."
            ),
        )
    )
    team_inclusie = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team Digitale Inclusie",
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
            naam="Team EU en Internationaal",
            type="team",
            parent_id=afd_strat_intl.id,
            beschrijving=(
                "EU-raden TTE Telecom, OECD digitaal beleid, bilaterale samenwerking."
            ),
        )
    )
    team_comm = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team Communicatie en Strategie",
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
            naam="Directie CIO Rijk",
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
            naam="Afdeling ICT-diensten en Voorzieningen",
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
            naam="Afdeling I-Stelsel en Vakmanschap",
            type="afdeling",
            parent_id=dir_cio.id,
            beschrijving=(
                "CIO-stelsel, enterprise-architectuur Rijk, NORA, digitaal vakmanschap."
            ),
        )
    )
    afd_infobev = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Afdeling Informatiebeveiliging",
            type="afdeling",
            parent_id=dir_cio.id,
            beschrijving=(
                "BIO-compliance, CISO Rijk, cyberveiligheid rijksoverheid en awareness."
            ),
        )
    )
    team_cloud = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team Cloud en Soevereiniteit",
            type="team",
            parent_id=afd_ict_voorz.id,
            beschrijving=(
                "Cloudbeleid, soevereine cloud, exit-strategieën en marktordening."
            ),
        )
    )
    team_sourcing = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team Sourcing en Leveranciersmanagement",
            type="team",
            parent_id=afd_ict_voorz.id,
            beschrijving=(
                "Regie op IT-leveranciers, marktordening en vendor lock-in preventie."
            ),
        )
    )
    team_arch = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team Architectuur en NORA",
            type="team",
            parent_id=afd_istelsel.id,
            beschrijving=(
                "Enterprise-architectuur Rijk, NORA-beheer en referentie-architecturen."
            ),
        )
    )
    team_cio_stelsel = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team CIO-stelsel",
            type="team",
            parent_id=afd_istelsel.id,
            beschrijving=(
                "CIO-overleg, nieuwe rollen CDO/CPO/CTO, governance-herziening."
            ),
        )
    )
    team_bio = await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Team BIO en Cyberveiligheid",
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
            naam="Directie Ambtenaar en Organisatie",
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
            naam="Afdeling Ambtelijk Vakmanschap en Rechtspositie",
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
            naam="Afdeling Arbeidsmarkt en Organisatie",
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
            naam="Team CAO en Arbeidsvoorwaarden",
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
            naam="Team Diversiteit en Inclusie",
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
            naam="Directie Inkoop-, Facilitair en Huisvestingsbeleid Rijk",
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
            naam="Afdeling Inkoop- en Aanbestedingsbeleid Rijk",
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
            naam="Afdeling Faciliteiten- en Huisvestingsbeleid",
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
            naam="Team Woo en Informatiehuishouding",
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
            naam="Team Actieplan Open Overheid",
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
            naam="Afdeling Zonder Mensen",
            type="afdeling",
            parent_id=dienst_dd.id,
            beschrijving="Geautomatiseerde processen en zelfbedieningsoplossingen.",
        )
    )

    # --- Bureau Architectuur Digitale Overheid (under Directie Digitale Overheid) ---
    await org_repo.create(
        OrganisatieEenheidCreate(
            naam="Bureau Architectuur Digitale Overheid",
            type="bureau",
            parent_id=dir_ddo.id,
            beschrijving=(
                "Architectuur en ontwerp voor digitale overheidsdienstverlening."
            ),
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
    # 2. PERSONEN (~200 medewerkers)
    # =========================================================================

    # Helper to create people in bulk
    async def cp(naam, email, functie, rol, eenheid):
        return await person_repo.create(
            PersonCreate(
                naam=naam,
                email=email,
                functie=functie,
                rol=rol,
                organisatie_eenheid_id=eenheid.id,
            )
        )

    # --- Bewindspersoon en ambtelijke top (echte namen) ---
    p_vanmarum = await cp(
        "Eddie van Marum",
        "e.vanmarum@minbzk.nl",
        "Staatssecretaris Digitalisering en Koninkrijksrelaties",
        "staatssecretaris",
        bzk,
    )
    p_dgdoo = await cp(
        "Eva den Dunnen-Heijblom",
        "e.dendunnen@minbzk.nl",
        "Directeur-Generaal Digitalisering en Overheidsorganisatie",
        "directeur_generaal",
        dgdoo,
    )

    # --- Directeuren (echte namen via ABD) ---
    p_vermeer = await cp(
        "Mark Vermeer",
        "m.vermeer@minbzk.nl",
        "Directeur Digitale Overheid",
        "directeur",
        dir_ddo,
    )
    p_beentjes = await cp(
        "Hillie Beentjes",
        "h.beentjes@minbzk.nl",
        "Directeur Digitale Samenleving / plv. DG DOO",
        "directeur",
        dir_ds,
    )
    p_deblaauw = await cp(
        "Art de Blaauw",
        "a.deblaauw@minbzk.nl",
        "Directeur CIO Rijk",
        "directeur",
        dir_cio,
    )
    p_weimar = await cp(
        "André Weimar",
        "a.weimar@minbzk.nl",
        "Wnd. directeur A&O / plv. DG Overheidsorganisatie",
        "directeur",
        dir_ao,
    )
    p_hulzebosch = await cp(
        "Mariya Hulzebosch",
        "m.hulzebosch@minbzk.nl",
        "Wnd. directeur IFHR / plv. DG Overheidsorganisatie",
        "directeur",
        dir_ifhr,
    )
    p_rutjens = await cp(
        "Jacqueline Rutjens",
        "j.rutjens@minbzk.nl",
        "Wnd. directeur Programma Open Overheid",
        "directeur",
        prog_open,
    )

    # --- Afdelingshoofden (ABD-benoemd, echte namen) ---
    # Digitale Overheid
    p_westelaken = await cp(
        "Lindy van de Westelaken",
        "l.vandewestelaken@minbzk.nl",
        "Afdelingshoofd Basisinfrastructuur en Dienstverlening",
        "afdelingshoofd",
        afd_basisinfra,
    )
    p_vanwissen = await cp(
        "Lissy van Wissen",
        "l.vanwissen@minbzk.nl",
        "Afdelingshoofd Identiteit en Toegang",
        "afdelingshoofd",
        afd_id_toegang,
    )

    # Digitale Samenleving
    p_kewal = await cp(
        "Suzie Kewal",
        "s.kewal@minbzk.nl",
        "Afdelingshoofd AI, Algoritmen, Data en Digitale Inclusie",
        "afdelingshoofd",
        afd_ai_data,
    )
    p_zondervan = await cp(
        "Ingrid Zondervan",
        "i.zondervan@minbzk.nl",
        "Afdelingshoofd Strategie, Internationaal en Communicatie",
        "afdelingshoofd",
        afd_strat_intl,
    )

    # CIO Rijk
    p_terborg = await cp(
        "Fleur ter Borg",
        "f.terborg@minbzk.nl",
        "Afdelingshoofd ICT-diensten en Voorzieningen",
        "afdelingshoofd",
        afd_ict_voorz,
    )
    # I-Stelsel en Vakmanschap — fictief
    p_brouwer = await cp(
        "Stefan Brouwer",
        "s.brouwer@minbzk.nl",
        "Afdelingshoofd I-Stelsel en Vakmanschap",
        "afdelingshoofd",
        afd_istelsel,
    )
    # Informatiebeveiliging — fictief
    p_timmermans = await cp(
        "Renate Timmermans",
        "r.timmermans@minbzk.nl",
        "Afdelingshoofd Informatiebeveiliging / CISO Rijk",
        "afdelingshoofd",
        afd_infobev,
    )

    # Ambtenaar & Organisatie
    p_vandegraaf = await cp(
        "Hester van de Graaf",
        "h.vandegraaf@minbzk.nl",
        "Afdelingshoofd Ambtelijk Vakmanschap en Rechtspositie",
        "afdelingshoofd",
        afd_ambt_vak,
    )
    # Arbeidsmarkt — fictief
    p_meijer = await cp(
        "Wouter Meijer",
        "w.meijer@minbzk.nl",
        "Afdelingshoofd Arbeidsmarkt en Organisatie",
        "afdelingshoofd",
        afd_arbeidsmarkt,
    )

    # IFHR
    p_zwaans = await cp(
        "David Zwaans",
        "d.zwaans@minbzk.nl",
        "Afdelingshoofd Inkoop- en Aanbestedingsbeleid Rijk",
        "afdelingshoofd",
        afd_inkoop,
    )
    p_coenen = await cp(
        "Irene Coenen",
        "i.coenen@minbzk.nl",
        "Afdelingshoofd Faciliteiten- en Huisvestingsbeleid",
        "afdelingshoofd",
        afd_fac_huisv,
    )

    # --- Teamleiders (fictief) ---
    p_tl_digid = await cp(
        "Priya Sharma",
        "p.sharma@minbzk.nl",
        "Teamleider DigiD Beleid",
        "coordinator",
        team_digid,
    )
    p_tl_eudiw = await cp(
        "Joost van Dijk",
        "j.vandijk@minbzk.nl",
        "Teamleider EUDIW",
        "coordinator",
        team_eudiw,
    )
    p_tl_mijnov = await cp(
        "Nienke Postma",
        "n.postma@minbzk.nl",
        "Teamleider MijnOverheid",
        "coordinator",
        team_mijnoverheid,
    )
    p_tl_gdi = await cp(
        "Rick Janssen",
        "r.janssen@minbzk.nl",
        "Teamleider GDI en Standaarden",
        "coordinator",
        team_gdi,
    )
    p_tl_algo = await cp(
        "Fatima Bakker-El Idrissi",
        "f.bakker@minbzk.nl",
        "Teamleider Algoritmeregister",
        "coordinator",
        team_algo,
    )
    p_tl_aiact = await cp(
        "Daan Vermeulen",
        "d.vermeulen@minbzk.nl",
        "Teamleider AI Act Implementatie",
        "coordinator",
        team_ai_act,
    )
    p_tl_data = await cp(
        "Samira El Amrani",
        "s.elamrani@minbzk.nl",
        "Teamleider Data en IBDS",
        "coordinator",
        team_data,
    )
    p_tl_incl = await cp(
        "Marjolein de Wit",
        "m.dewit@minbzk.nl",
        "Teamleider Digitale Inclusie",
        "coordinator",
        team_inclusie,
    )
    p_tl_eu = await cp(
        "Pieter-Jan Hofstra",
        "pj.hofstra@minbzk.nl",
        "Teamleider EU en Internationaal",
        "coordinator",
        team_eu_intl,
    )
    p_tl_comm = await cp(
        "Lisa van Beek",
        "l.vanbeek@minbzk.nl",
        "Teamleider Communicatie en Strategie",
        "coordinator",
        team_comm,
    )
    p_tl_cloud = await cp(
        "Bas Hendriks",
        "b.hendriks@minbzk.nl",
        "Teamleider Cloud en Soevereiniteit",
        "coordinator",
        team_cloud,
    )
    p_tl_sourc = await cp(
        "Eva Jansen",
        "e.jansen@minbzk.nl",
        "Teamleider Sourcing en Leveranciersmanagement",
        "coordinator",
        team_sourcing,
    )
    p_tl_arch = await cp(
        "Jeroen Smit",
        "j.smit@minbzk.nl",
        "Teamleider Architectuur en NORA",
        "coordinator",
        team_arch,
    )
    p_tl_ciostel = await cp(
        "Annemiek Vos",
        "a.vos@minbzk.nl",
        "Teamleider CIO-stelsel",
        "coordinator",
        team_cio_stelsel,
    )
    p_tl_bio = await cp(
        "Sander Kuijpers",
        "s.kuijpers@minbzk.nl",
        "Teamleider BIO en Cyberveiligheid",
        "coordinator",
        team_bio,
    )
    p_tl_cao = await cp(
        "Mirjam Schouten",
        "m.schouten@minbzk.nl",
        "Teamleider CAO en Arbeidsvoorwaarden",
        "coordinator",
        team_cao,
    )
    p_tl_div = await cp(
        "Omar Yilmaz",
        "o.yilmaz@minbzk.nl",
        "Teamleider Diversiteit en Inclusie",
        "coordinator",
        team_diversiteit,
    )
    p_tl_woo = await cp(
        "Charlotte Dekker",
        "c.dekker@minbzk.nl",
        "Teamleider Woo en Informatiehuishouding",
        "coordinator",
        team_woo,
    )
    p_tl_actie = await cp(
        "Tim Groenewegen",
        "t.groenewegen@minbzk.nl",
        "Teamleider Actieplan Open Overheid",
        "coordinator",
        team_actieplan,
    )

    # --- Senior beleidsmedewerkers en beleidsmedewerkers (fictief, ~150 personen) ---
    # Bulk data: (naam, email prefix, functie, rol, eenheid)
    bulk_people = [
        # === Directie Digitale Overheid — Afd Basisinfra (~12) ===
        (
            "Sophie van der Linden",
            "s.vanderlinden",
            "Senior beleidsmedewerker GDI",
            "senior_beleidsmedewerker",
            team_gdi,
        ),
        (
            "Thomas Bakker",
            "t.bakker",
            "Beleidsmedewerker basisregistraties",
            "beleidsmedewerker",
            team_gdi,
        ),
        (
            "Anouk Willems",
            "a.willems",
            "Beleidsmedewerker standaarden",
            "beleidsmedewerker",
            team_gdi,
        ),
        (
            "Marloes Visser",
            "m.visser",
            "Projectleider MijnOverheid doorontwikkeling",
            "projectleider",
            team_mijnoverheid,
        ),
        (
            "Ravi Patel",
            "r.patel",
            "Senior beleidsmedewerker MijnOverheid",
            "senior_beleidsmedewerker",
            team_mijnoverheid,
        ),
        (
            "Dominique Leroy",
            "d.leroy",
            "Beleidsmedewerker berichtenbox",
            "beleidsmedewerker",
            team_mijnoverheid,
        ),
        (
            "Fleur Mulder",
            "f.mulder",
            "Beleidsmedewerker machtigen",
            "beleidsmedewerker",
            team_mijnoverheid,
        ),
        (
            "Youssef Amrani",
            "y.amrani",
            "Beleidsmedewerker lopende zaken",
            "beleidsmedewerker",
            afd_basisinfra,
        ),
        (
            "Wietske Nauta",
            "w.nauta",
            "Directiesecretaris Digitale Overheid",
            "beleidsmedewerker",
            afd_basisinfra,
        ),
        (
            "Jasper van Leeuwen",
            "j.vanleeuwen",
            "Beleidsmedewerker toegankelijkheid",
            "beleidsmedewerker",
            afd_basisinfra,
        ),
        # === Afd Identiteit en Toegang (~14) ===
        (
            "Deniz Kaya",
            "d.kaya",
            "Senior beleidsmedewerker digitale identiteit",
            "senior_beleidsmedewerker",
            afd_id_toegang,
        ),
        (
            "Floor Dijkstra",
            "f.dijkstra",
            "Senior beleidsmedewerker eIDAS",
            "senior_beleidsmedewerker",
            afd_id_toegang,
        ),
        (
            "Linh Nguyen",
            "l.nguyen",
            "Beleidsmedewerker DigiD",
            "beleidsmedewerker",
            team_digid,
        ),
        (
            "Koen Janssen",
            "k.janssen",
            "Beleidsmedewerker DigiD Hoog",
            "beleidsmedewerker",
            team_digid,
        ),
        (
            "Sara Molenaar",
            "s.molenaar",
            "Beleidsmedewerker DigiD Machtigen",
            "beleidsmedewerker",
            team_digid,
        ),
        (
            "Thijs de Boer",
            "th.deboer",
            "Senior beleidsmedewerker EUDIW",
            "senior_beleidsmedewerker",
            team_eudiw,
        ),
        (
            "Nina Aerts",
            "n.aerts",
            "Beleidsmedewerker wallet architectuur",
            "beleidsmedewerker",
            team_eudiw,
        ),
        (
            "Maarten Vos",
            "m.vos",
            "Beleidsmedewerker eIDAS2-implementatie",
            "beleidsmedewerker",
            team_eudiw,
        ),
        (
            "Emma van Dalen",
            "e.vandalen",
            "Beleidsmedewerker pilotprogramma EUDIW",
            "beleidsmedewerker",
            team_eudiw,
        ),
        (
            "Ruben Groen",
            "r.groen",
            "Beleidsmedewerker elektronische handtekeningen",
            "beleidsmedewerker",
            afd_id_toegang,
        ),
        # === Afd WDO (~8) ===
        (
            "Lisa Achterberg",
            "l.achterberg",
            "Juridisch adviseur digitale grondrechten",
            "jurist",
            afd_wdo,
        ),
        (
            "Vincent Bos",
            "v.bos",
            "Senior juridisch medewerker WDO",
            "senior_beleidsmedewerker",
            afd_wdo,
        ),
        (
            "Manon Kuiper",
            "m.kuiper",
            "Beleidsmedewerker interoperabiliteitswet",
            "beleidsmedewerker",
            afd_wdo,
        ),
        (
            "Alexander Scholten",
            "a.scholten",
            "Beleidsmedewerker stelselwetgeving",
            "beleidsmedewerker",
            afd_wdo,
        ),
        (
            "Julia van Houten",
            "j.vanhouten",
            "Juridisch medewerker WDO transitie",
            "jurist",
            afd_wdo,
        ),
        (
            "Bart Koster",
            "b.koster",
            "Beleidsmedewerker rechtsbescherming",
            "beleidsmedewerker",
            afd_wdo,
        ),
        # === Directie Digitale Samenleving — Afd AI/Data/Inclusie (~20) ===
        (
            "Bram de Jong",
            "b.dejong",
            "Senior beleidsmedewerker AI-verordening",
            "senior_beleidsmedewerker",
            team_ai_act,
        ),
        (
            "Raj Kumar",
            "r.kumar",
            "Senior beleidsmedewerker data en IBDS",
            "senior_beleidsmedewerker",
            team_data,
        ),
        (
            "Anne Hendriks",
            "a.hendriks",
            "Beleidsmedewerker digitale inclusie",
            "beleidsmedewerker",
            team_inclusie,
        ),
        (
            "Naomi Osei",
            "n.osei",
            "Beleidsmedewerker Algoritmeregister",
            "beleidsmedewerker",
            team_algo,
        ),
        (
            "Sven Berger",
            "s.berger",
            "Beleidsmedewerker algoritmekader",
            "beleidsmedewerker",
            team_algo,
        ),
        (
            "Iris van Dam",
            "i.vandam",
            "Beleidsmedewerker impactassessment algoritmen",
            "beleidsmedewerker",
            team_algo,
        ),
        (
            "Mike Koopman",
            "m.koopman",
            "Senior beleidsmedewerker AI Act hoog-risico",
            "senior_beleidsmedewerker",
            team_ai_act,
        ),
        (
            "Femke Admiraal",
            "f.admiraal",
            "Beleidsmedewerker generatieve AI",
            "beleidsmedewerker",
            team_ai_act,
        ),
        (
            "Leon Groot",
            "l.groot",
            "Beleidsmedewerker AI toezicht",
            "beleidsmedewerker",
            team_ai_act,
        ),
        (
            "Carmen Torres",
            "c.torres",
            "Senior beleidsmedewerker IBDS afsprakenstelsel",
            "senior_beleidsmedewerker",
            team_data,
        ),
        (
            "Jesse van Rijn",
            "j.vanrijn",
            "Beleidsmedewerker Federatief Datastelsel",
            "beleidsmedewerker",
            team_data,
        ),
        (
            "Esra Yildirim",
            "e.yildirim",
            "Beleidsmedewerker open data",
            "beleidsmedewerker",
            team_data,
        ),
        (
            "Hanneke Prins",
            "h.prins",
            "Senior beleidsmedewerker digitale geletterdheid",
            "senior_beleidsmedewerker",
            team_inclusie,
        ),
        (
            "Jan-Willem Moerman",
            "jw.moerman",
            "Beleidsmedewerker digibeten programma",
            "beleidsmedewerker",
            team_inclusie,
        ),
        (
            "Lot van Dongen",
            "l.vandongen",
            "Beleidsmedewerker toegankelijkheid overheid",
            "beleidsmedewerker",
            team_inclusie,
        ),
        # === Afd Strategie/Internationaal/Communicatie (~10) ===
        (
            "Mees Hoekstra",
            "m.hoekstra",
            "Senior beleidsmedewerker NDS coördinatie",
            "senior_beleidsmedewerker",
            team_comm,
        ),
        (
            "Luuk Driessen",
            "l.driessen",
            "Communicatieadviseur digitalisering",
            "communicatieadviseur",
            team_comm,
        ),
        (
            "Petra Claassen",
            "p.claassen",
            "Senior beleidsmedewerker EU TTE",
            "senior_beleidsmedewerker",
            team_eu_intl,
        ),
        (
            "Freek van der Heijden",
            "f.vanderheijden",
            "Beleidsmedewerker OECD digitaal",
            "beleidsmedewerker",
            team_eu_intl,
        ),
        (
            "Lieke Vermolen",
            "l.vermolen",
            "Beleidsmedewerker internationale digitalisering",
            "beleidsmedewerker",
            team_eu_intl,
        ),
        (
            "Bob Gerrits",
            "b.gerrits",
            "Beleidsmedewerker stakeholdermanagement",
            "beleidsmedewerker",
            team_comm,
        ),
        (
            "Nikki Rodenburg",
            "n.rodenburg",
            "Directiesecretaris Digitale Samenleving",
            "beleidsmedewerker",
            afd_strat_intl,
        ),
        (
            "Matthijs Born",
            "m.born",
            "Beleidsmedewerker digitale grondrechten",
            "beleidsmedewerker",
            afd_strat_intl,
        ),
        # === Directie CIO Rijk — Afd ICT-diensten (~12) ===
        (
            "Karin de Vries",
            "k.devries",
            "Senior beleidsmedewerker cloudbeleid",
            "senior_beleidsmedewerker",
            team_cloud,
        ),
        (
            "Patrick Oomen",
            "p.oomen",
            "Beleidsmedewerker soevereine cloud",
            "beleidsmedewerker",
            team_cloud,
        ),
        (
            "Daniëlle Moerland",
            "d.moerland",
            "Beleidsmedewerker datacentersstrategie",
            "beleidsmedewerker",
            team_cloud,
        ),
        (
            "Tom Willemse",
            "t.willemse",
            "Beleidsmedewerker exit-strategieën",
            "beleidsmedewerker",
            team_cloud,
        ),
        (
            "Inge Westra",
            "i.westra",
            "Senior beleidsmedewerker leveranciersmanagement",
            "senior_beleidsmedewerker",
            team_sourcing,
        ),
        (
            "Arjan de Haan",
            "a.dehaan",
            "Beleidsmedewerker IT-marktordening",
            "beleidsmedewerker",
            team_sourcing,
        ),
        (
            "Sandra Muijs",
            "s.muijs",
            "Beleidsmedewerker vendor lock-in",
            "beleidsmedewerker",
            team_sourcing,
        ),
        (
            "Wesley Kort",
            "w.kort",
            "CTO adviseur technische standaarden",
            "adviseur",
            afd_ict_voorz,
        ),
        # === Afd I-Stelsel en Vakmanschap (~10) ===
        (
            "Michelle Langenberg",
            "m.langenberg",
            "Senior enterprise architect Rijk",
            "senior_beleidsmedewerker",
            team_arch,
        ),
        ("Robert Kok", "r.kok", "NORA-beheerder", "adviseur", team_arch),
        (
            "Vera Gielen",
            "v.gielen",
            "Beleidsmedewerker referentie-architectuur",
            "beleidsmedewerker",
            team_arch,
        ),
        (
            "Frank Polman",
            "f.polman",
            "Senior beleidsmedewerker CIO-stelsel",
            "senior_beleidsmedewerker",
            team_cio_stelsel,
        ),
        (
            "Greta van Rooij",
            "g.vanrooij",
            "Beleidsmedewerker CIO-overleg",
            "beleidsmedewerker",
            team_cio_stelsel,
        ),
        (
            "Henri Manders",
            "h.manders",
            "Beleidsmedewerker digitaal vakmanschap",
            "beleidsmedewerker",
            team_cio_stelsel,
        ),
        (
            "Annelies Boom",
            "a.boom",
            "Beleidsmedewerker I-strategie",
            "beleidsmedewerker",
            afd_istelsel,
        ),
        # === Afd Informatiebeveiliging (~8) ===
        (
            "Thomas van den Berg",
            "t.vandenberg",
            "Senior beleidsmedewerker BIO",
            "senior_beleidsmedewerker",
            team_bio,
        ),
        (
            "Erik Huizen",
            "e.huizen",
            "Beleidsmedewerker cyberveiligheid Rijk",
            "beleidsmedewerker",
            team_bio,
        ),
        (
            "Linda Verhoeven",
            "l.verhoeven",
            "Beleidsmedewerker security awareness",
            "beleidsmedewerker",
            team_bio,
        ),
        (
            "Marco Fontein",
            "m.fontein",
            "Senior beleidsmedewerker audits en compliance",
            "senior_beleidsmedewerker",
            afd_infobev,
        ),
        (
            "Yvette Claessens",
            "y.claessens",
            "Beleidsmedewerker incidentrespons",
            "beleidsmedewerker",
            afd_infobev,
        ),
        (
            "Niels Borgman",
            "n.borgman",
            "Beleidsmedewerker dreigingsanalyse",
            "beleidsmedewerker",
            afd_infobev,
        ),
        # === Directie A&O (~15) ===
        (
            "Maarten Peeters",
            "m.peeters",
            "Senior beleidsmedewerker HR Rijksdienst",
            "senior_beleidsmedewerker",
            afd_arbeidsmarkt,
        ),
        (
            "Leonie Mulder",
            "l.mulder",
            "Beleidsmedewerker arbeidsmarktcommunicatie",
            "beleidsmedewerker",
            afd_arbeidsmarkt,
        ),
        (
            "Jasper Hoekman",
            "j.hoekman",
            "Beleidsmedewerker talentprogramma's",
            "beleidsmedewerker",
            afd_arbeidsmarkt,
        ),
        (
            "Monique Geerts",
            "m.geerts",
            "Senior beleidsmedewerker CAO Rijk",
            "senior_beleidsmedewerker",
            team_cao,
        ),
        (
            "Arno Willems",
            "a2.willems",
            "Beleidsmedewerker pensioenen en sociale zekerheid",
            "beleidsmedewerker",
            team_cao,
        ),
        (
            "Claire van Beek",
            "c.vanbeek",
            "Beleidsmedewerker salarisbeleid",
            "beleidsmedewerker",
            team_cao,
        ),
        (
            "Said Benali",
            "s.benali",
            "Senior beleidsmedewerker ambtelijk vakmanschap",
            "senior_beleidsmedewerker",
            afd_ambt_vak,
        ),
        (
            "Tanja Veldkamp",
            "t.veldkamp",
            "Juridisch medewerker Ambtenarenwet",
            "jurist",
            afd_ambt_vak,
        ),
        (
            "Kim Janson",
            "k.janson",
            "Beleidsmedewerker integriteit",
            "beleidsmedewerker",
            afd_ambt_vak,
        ),
        (
            "Yusuf Arslan",
            "y.arslan",
            "Senior beleidsmedewerker banenafspraak",
            "senior_beleidsmedewerker",
            team_diversiteit,
        ),
        (
            "Noor de Groot",
            "n.degroot",
            "Beleidsmedewerker inclusief werkgeverschap",
            "beleidsmedewerker",
            team_diversiteit,
        ),
        (
            "Dirk Aalbers",
            "d.aalbers",
            "Beleidsmedewerker organisatieontwikkeling",
            "beleidsmedewerker",
            afd_arbeidsmarkt,
        ),
        (
            "Patricia Volkers",
            "p.volkers",
            "Directiesecretaris A&O",
            "beleidsmedewerker",
            dir_ao,
        ),
        # === Directie IFHR (~15) ===
        (
            "Chantal Gorter",
            "c.gorter",
            "Senior beleidsmedewerker MVI",
            "senior_beleidsmedewerker",
            afd_inkoop,
        ),
        (
            "Hugo Verwey",
            "h.verwey",
            "Beleidsmedewerker aanbestedingsrecht",
            "beleidsmedewerker",
            afd_inkoop,
        ),
        (
            "Renée van Vliet",
            "r.vanvliet",
            "Beleidsmedewerker categoriemanagement",
            "beleidsmedewerker",
            afd_inkoop,
        ),
        (
            "Stan Molenaar",
            "s2.molenaar",
            "Beleidsmedewerker IT-inkoop",
            "beleidsmedewerker",
            afd_inkoop,
        ),
        (
            "Wendy Driessen",
            "w.driessen",
            "Senior beleidsmedewerker rijkshuisvesting",
            "senior_beleidsmedewerker",
            afd_fac_huisv,
        ),
        (
            "Karel Mertens",
            "k.mertens",
            "Beleidsmedewerker hybride werken",
            "beleidsmedewerker",
            afd_fac_huisv,
        ),
        (
            "Astrid van Hoorn",
            "a.vanhoorn",
            "Beleidsmedewerker verduurzaming kantoren",
            "beleidsmedewerker",
            afd_fac_huisv,
        ),
        (
            "Rutger Bosman",
            "r.bosman",
            "Beleidsmedewerker facilitaire dienstverlening",
            "beleidsmedewerker",
            afd_fac_huisv,
        ),
        (
            "Debby Konings",
            "d.konings",
            "Directiesecretaris IFHR",
            "beleidsmedewerker",
            dir_ifhr,
        ),
        # === Programma Open Overheid (~10) ===
        (
            "Mireille Pastoor",
            "m.pastoor",
            "Senior beleidsmedewerker Woo",
            "senior_beleidsmedewerker",
            team_woo,
        ),
        (
            "Gerben Zijlstra",
            "g.zijlstra",
            "Beleidsmedewerker actieve openbaarmaking",
            "beleidsmedewerker",
            team_woo,
        ),
        (
            "Ilse Vermeer",
            "i.vermeer",
            "Beleidsmedewerker informatiehuishouding",
            "beleidsmedewerker",
            team_woo,
        ),
        (
            "Robin van Es",
            "r.vanes",
            "Senior beleidsmedewerker OGP",
            "senior_beleidsmedewerker",
            team_actieplan,
        ),
        (
            "Sanne Lammers",
            "s.lammers",
            "Beleidsmedewerker actieplan",
            "beleidsmedewerker",
            team_actieplan,
        ),
        (
            "Max Verbeek",
            "m.verbeek",
            "Beleidsmedewerker participatie",
            "beleidsmedewerker",
            team_actieplan,
        ),
        (
            "Lotte Verduin",
            "l.verduin",
            "Programmasecretaris Open Overheid",
            "beleidsmedewerker",
            prog_open,
        ),
        # === DG-staf / overkoepelend (~8) ===
        ("Eline Modderman", "e.modderman", "DG-secretaris", "adviseur", dgdoo),
        ("Derk Ottens", "d.ottens", "Strategisch adviseur DG", "adviseur", dgdoo),
        (
            "Felien de Vos",
            "f.devos",
            "Managementassistent DG",
            "beleidsmedewerker",
            dgdoo,
        ),
        (
            "Huub Geelen",
            "h.geelen",
            "Parlementair liaison digitalisering",
            "adviseur",
            dgdoo,
        ),
        ("Willeke Post", "w.post", "Controller DGDOO", "adviseur", dgdoo),
        (
            "Jacob Tervoort",
            "j.tervoort",
            "Communicatieadviseur DGDOO",
            "communicatieadviseur",
            dgdoo,
        ),
        # === Extra beleidsmedewerkers Digitale Overheid (~10) ===
        (
            "Wouter van Eijk",
            "w.vaneijk",
            "Beleidsmedewerker DigiD Hoog roadmap",
            "beleidsmedewerker",
            team_digid,
        ),
        (
            "Rosa Bakker",
            "r.bakker",
            "Beleidsmedewerker authenticatie-aansluiting",
            "beleidsmedewerker",
            team_digid,
        ),
        (
            "Amir Hassan",
            "a.hassan",
            "Beleidsmedewerker EUDIW privacykader",
            "beleidsmedewerker",
            team_eudiw,
        ),
        (
            "Tineke van der Wal",
            "t.vanderwal",
            "Beleidsmedewerker GDI governance",
            "beleidsmedewerker",
            team_gdi,
        ),
        (
            "Stefan Groot",
            "s.groot",
            "Beleidsmedewerker basisregistraties koppelvlak",
            "beleidsmedewerker",
            team_gdi,
        ),
        (
            "Naomi Veen",
            "n.veen",
            "Beleidsmedewerker MijnOverheid app",
            "beleidsmedewerker",
            team_mijnoverheid,
        ),
        (
            "Jip Aldenberg",
            "j.aldenberg",
            "Beleidsmedewerker WDO transitiebegeleiding",
            "beleidsmedewerker",
            afd_wdo,
        ),
        (
            "Lara Koppers",
            "l.koppers",
            "Beleidsmedewerker WDO handhaving",
            "beleidsmedewerker",
            afd_wdo,
        ),
        (
            "Daan van Houten",
            "d.vanhouten",
            "Beleidsmedewerker basisinfra monitoring",
            "beleidsmedewerker",
            afd_basisinfra,
        ),
        (
            "Merel Franken",
            "m.franken",
            "Beleidsmedewerker digitale toegankelijkheid",
            "beleidsmedewerker",
            afd_basisinfra,
        ),
        # === Extra beleidsmedewerkers Digitale Samenleving (~10) ===
        (
            "Khalid Bensaid",
            "k.bensaid",
            "Beleidsmedewerker AI-ethiek",
            "beleidsmedewerker",
            team_ai_act,
        ),
        (
            "Jolien Verstappen",
            "j.verstappen",
            "Beleidsmedewerker AI sandbox",
            "beleidsmedewerker",
            team_ai_act,
        ),
        (
            "Olaf Kuijpers",
            "o.kuijpers",
            "Beleidsmedewerker algoritmeverificatie",
            "beleidsmedewerker",
            team_algo,
        ),
        (
            "Isa de Bruijn",
            "i.debruijn",
            "Beleidsmedewerker open algoritmen",
            "beleidsmedewerker",
            team_algo,
        ),
        (
            "Timo van Dijk",
            "t.vandijk",
            "Beleidsmedewerker datakwaliteit",
            "beleidsmedewerker",
            team_data,
        ),
        (
            "Femke Bierens",
            "f.bierens",
            "Beleidsmedewerker high-value datasets",
            "beleidsmedewerker",
            team_data,
        ),
        (
            "Yousra El Moussaoui",
            "y.elmoussaoui",
            "Beleidsmedewerker digivaardig op school",
            "beleidsmedewerker",
            team_inclusie,
        ),
        (
            "Pieter Voogd",
            "p.voogd",
            "Beleidsmedewerker NDS doelarchitectuur",
            "beleidsmedewerker",
            team_comm,
        ),
        (
            "Karlijn Oomen",
            "k.oomen",
            "Beleidsmedewerker EU Digital Decade",
            "beleidsmedewerker",
            team_eu_intl,
        ),
        (
            "Florian Gerritse",
            "f.gerritse",
            "Beleidsmedewerker digitaal partnerschap",
            "beleidsmedewerker",
            team_eu_intl,
        ),
        # === Extra beleidsmedewerkers CIO Rijk (~10) ===
        (
            "Sietse Hoekema",
            "s.hoekema",
            "Beleidsmedewerker GenAI governance",
            "beleidsmedewerker",
            team_cloud,
        ),
        (
            "Nadia Soufiani",
            "n.soufiani",
            "Beleidsmedewerker cloud security",
            "beleidsmedewerker",
            team_cloud,
        ),
        (
            "Victor Blom",
            "v.blom",
            "Beleidsmedewerker IT-contractrecht",
            "beleidsmedewerker",
            team_sourcing,
        ),
        (
            "Britt Aalders",
            "b.aalders",
            "Beleidsmedewerker CIO-dashboard",
            "beleidsmedewerker",
            team_cio_stelsel,
        ),
        (
            "Ruud Janssen",
            "r2.janssen",
            "Beleidsmedewerker NORA doorontwikkeling",
            "beleidsmedewerker",
            team_arch,
        ),
        (
            "Elise van Rooijen",
            "e.vanrooijen",
            "Beleidsmedewerker pentesting beleid",
            "beleidsmedewerker",
            team_bio,
        ),
        (
            "Maurice Franssen",
            "m.franssen",
            "Beleidsmedewerker zero trust architectuur",
            "beleidsmedewerker",
            afd_infobev,
        ),
        (
            "Daphne Kramer",
            "d.kramer",
            "Beleidsmedewerker informatiebeveiligingsaudits",
            "beleidsmedewerker",
            afd_infobev,
        ),
        (
            "Joris de Lange",
            "j.delange",
            "Beleidsmedewerker CDO/CPO implementatie",
            "beleidsmedewerker",
            team_cio_stelsel,
        ),
        (
            "Imke Verhagen",
            "i.verhagen",
            "Beleidsmedewerker digitaal vakmanschap Rijk",
            "beleidsmedewerker",
            afd_istelsel,
        ),
        # === Extra beleidsmedewerkers A&O (~8) ===
        (
            "Stefan Kamp",
            "s.kamp",
            "Beleidsmedewerker modern werkgeverschap",
            "beleidsmedewerker",
            afd_arbeidsmarkt,
        ),
        (
            "Liza Veldman",
            "l.veldman",
            "Beleidsmedewerker WNT en topinkomens",
            "beleidsmedewerker",
            afd_ambt_vak,
        ),
        (
            "Dennis Roelofs",
            "d.roelofs",
            "Beleidsmedewerker integriteitsbeleid Rijk",
            "beleidsmedewerker",
            afd_ambt_vak,
        ),
        (
            "Wilma Koetse",
            "w.koetse",
            "Beleidsmedewerker traineeprogramma Rijksdienst",
            "beleidsmedewerker",
            afd_arbeidsmarkt,
        ),
        (
            "Thom Dijkema",
            "t.dijkema",
            "Beleidsmedewerker hybride werken beleid",
            "beleidsmedewerker",
            team_diversiteit,
        ),
        (
            "Samantha Pool",
            "s.pool",
            "Beleidsmedewerker cultuursensitief werken",
            "beleidsmedewerker",
            team_diversiteit,
        ),
        (
            "Kevin Bakx",
            "k.bakx",
            "Beleidsmedewerker CAO onderhandeling",
            "beleidsmedewerker",
            team_cao,
        ),
        (
            "Nienke Dijkhuizen",
            "n.dijkhuizen",
            "Beleidsmedewerker sociale zekerheid ambtenaren",
            "beleidsmedewerker",
            team_cao,
        ),
        # === Extra beleidsmedewerkers IFHR + Open Overheid (~8) ===
        (
            "Laura Bontekoe",
            "l.bontekoe",
            "Beleidsmedewerker circulair inkopen",
            "beleidsmedewerker",
            afd_inkoop,
        ),
        (
            "Gijs Schuurman",
            "g.schuurman",
            "Beleidsmedewerker rijkshuisvesting verduurzaming",
            "beleidsmedewerker",
            afd_fac_huisv,
        ),
        (
            "Marleen Jonker",
            "m.jonker",
            "Beleidsmedewerker flexwerkplekken Rijk",
            "beleidsmedewerker",
            afd_fac_huisv,
        ),
        (
            "Otto Prins",
            "o.prins",
            "Beleidsmedewerker Woo-verzoeken analyse",
            "beleidsmedewerker",
            team_woo,
        ),
        (
            "Nathalie Hendriks",
            "n2.hendriks",
            "Beleidsmedewerker informatiehuishouding standaarden",
            "beleidsmedewerker",
            team_woo,
        ),
        (
            "Casper Bloemendaal",
            "c.bloemendaal",
            "Beleidsmedewerker actieplan transparantie",
            "beleidsmedewerker",
            team_actieplan,
        ),
        (
            "Elisabeth Vink",
            "e.vink",
            "Beleidsmedewerker open spending",
            "beleidsmedewerker",
            team_actieplan,
        ),
        (
            "Mark de Wolf",
            "m.dewolf",
            "Beleidsmedewerker MVI sociale voorwaarden",
            "beleidsmedewerker",
            afd_inkoop,
        ),
        # === Bestuursstaf BZK (~4) ===
        (
            "Marie-Claire Bouwhuis",
            "mc.bouwhuis",
            "Parlementair adviseur BZK",
            "adviseur",
            staf_bzk,
        ),
        (
            "Hans Rietdijk",
            "h.rietdijk",
            "Woordvoerder digitalisering BZK",
            "communicatieadviseur",
            staf_bzk,
        ),
        (
            "Bert Kamphuis",
            "b.kamphuis",
            "Juridisch adviseur digitaal recht",
            "jurist",
            staf_bzk,
        ),
        (
            "Anke Tersteeg",
            "a.tersteeg",
            "Beleidscoördinator SG-staf",
            "adviseur",
            staf_bzk,
        ),
    ]

    p_linden = None
    p_kaya = None
    p_nguyen = None
    p_visser = None
    p_dejong = None
    p_bakker = p_tl_algo
    p_kumar = None
    p_hendriks = None
    p_smit = p_tl_arch
    p_devries = None
    p_berg = None
    p_jansen = p_tl_sourc
    p_peeters = None
    p_achterberg = None

    for naam, email_prefix, functie, rol, eenheid in bulk_people:
        p = await cp(naam, f"{email_prefix}@minbzk.nl", functie, rol, eenheid)
        # Keep references to key people for tasks
        if email_prefix == "s.vanderlinden":
            p_linden = p
        elif email_prefix == "d.kaya":
            p_kaya = p
        elif email_prefix == "l.nguyen":
            p_nguyen = p
        elif email_prefix == "m.visser":
            p_visser = p
        elif email_prefix == "b.dejong":
            p_dejong = p
        elif email_prefix == "r.kumar":
            p_kumar = p
        elif email_prefix == "a.hendriks":
            p_hendriks = p
        elif email_prefix == "k.devries":
            p_devries = p
        elif email_prefix == "t.vandenberg":
            p_berg = p
        elif email_prefix == "m.peeters":
            p_peeters = p
        elif email_prefix == "l.achterberg":
            p_achterberg = p

    person_count = (
        8 + 11 + 20 + len(bulk_people)
    )  # top + afdelingshoofden + teamleiders + bulk
    print(f"  Personen: {person_count} personen aangemaakt")

    # =========================================================================
    # 2a. AGENTS
    # =========================================================================

    async def create_agent(naam, functie, eenheid, rol="beleidsmedewerker"):
        api_key = f"bm_{''.join(f'{b:02x}' for b in uuid.uuid4().bytes[:16])}"
        return await person_repo.create(
            PersonCreate(
                naam=naam,
                functie=functie,
                rol=rol,
                organisatie_eenheid_id=eenheid.id,
                is_agent=True,
                api_key=api_key,
            )
        )

    # Domain-specialist agents in "Afdeling Zonder Mensen"
    # Named after characters from Bordewijk's novel "Karakter"
    agent_identiteit = await create_agent(
        "Dreverhaven",
        "Beleidsmedewerker digitale identiteit en authenticatie (eID, DigiD, eIDAS)",
        afd_zonder_mensen,
        rol="afdelingshoofd",
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
        rol="adviseur",
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
        (bzk, p_vanmarum),
        (dgdoo, p_dgdoo),
        (dir_ddo, p_vermeer),
        (dir_ds, p_beentjes),
        (dir_cio, p_deblaauw),
        (dir_ao, p_weimar),
        (dir_ifhr, p_hulzebosch),
        (prog_open, p_rutjens),
        # Afdelingshoofden (ABD-benoemd)
        (afd_basisinfra, p_westelaken),
        (afd_id_toegang, p_vanwissen),
        (afd_wdo, p_linden),
        (afd_ai_data, p_kewal),
        (afd_strat_intl, p_zondervan),
        (afd_ict_voorz, p_terborg),
        (afd_istelsel, p_brouwer),
        (afd_infobev, p_timmermans),
        (afd_ambt_vak, p_vandegraaf),
        (afd_arbeidsmarkt, p_meijer),
        (afd_inkoop, p_zwaans),
        (afd_fac_huisv, p_coenen),
        # Teamleiders
        (team_digid, p_tl_digid),
        (team_eudiw, p_tl_eudiw),
        (team_mijnoverheid, p_tl_mijnov),
        (team_gdi, p_tl_gdi),
        (team_algo, p_tl_algo),
        (team_ai_act, p_tl_aiact),
        (team_data, p_tl_data),
        (team_inclusie, p_tl_incl),
        (team_eu_intl, p_tl_eu),
        (team_comm, p_tl_comm),
        (team_cloud, p_tl_cloud),
        (team_sourcing, p_tl_sourc),
        (team_arch, p_tl_arch),
        (team_cio_stelsel, p_tl_ciostel),
        (team_bio, p_tl_bio),
        (team_cao, p_tl_cao),
        (team_diversiteit, p_tl_div),
        (team_woo, p_tl_woo),
        (team_actieplan, p_tl_actie),
        (afd_zonder_mensen, agent_identiteit),
    ]
    for unit, manager in manager_assignments:
        unit.manager_id = manager.id
    await db.flush()

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
            title="Dossier AI en Algoritmen",
            node_type="dossier",
            description=(
                "Overheidsinzet van AI, algoritmetoezicht,"
                " AI-verordening implementatie en verantwoord gebruik."
            ),
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
            description=(
                "Wettelijk kader voor veilig inloggen bij de overheid en "
                "beveiligingsnormen. Gefaseerd van kracht sinds 1 juli 2023. "
                "Overgangstermijn verlengd tot 1 juli 2028."
                " DigiD Machtigen als publiek machtigingsstelsel."
            ),
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
            title="Rijksbreed Cloudbeleid 2024",
            node_type="beleidskader",
            description=(
                "Kader voor verantwoord cloudgebruik door de rijksoverheid. "
                "Classificatiemodel voor gegevens, soevereiniteitsvereisten en "
                "exit-strategieën. Basis voor NDS-pijler Cloud."
            ),
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
            title="1500 algoritmen geregistreerd in Algoritmeregister",
            node_type="doel",
            description=(
                "Doelstelling om per eind 2026 minimaal 1500"
                " impactvolle algoritmen van overheidsorganisaties"
                " gepubliceerd te hebben in het Algoritmeregister."
            ),
        )
    )
    doel_eudiw = await node_repo.create(
        CorpusNodeCreate(
            title="Europese Digitale Identiteit Wallet (EUDIW) gereed",
            node_type="doel",
            description=(
                "Nederland levert een werkende EUDIW-implementatie conform de herziene "
                "eIDAS2-verordening, uiterlijk 2027. Pilot in 2026."
            ),
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
            description=(
                "Rijksbreed 30% reductie in afhankelijkheid van"
                " externe IT-leveranciers door structurele"
                " versterking van interne IT-capaciteit. Onderdeel"
                "regeerprogramma."
            ),
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
            p_nguyen,
            "in_progress",
            "hoog",
            date(2026, 3, 15),
            afd_id_toegang,
            [
                (
                    "Inventarisatie NFC-chip types in omloop",
                    p_nguyen, "done", "normaal", date(2026, 2, 15),
                ),
                (
                    "Test NFC-uitlezing op Android-toestellen",
                    p_nguyen, "in_progress", "hoog", date(2026, 3, 1),
                ),
                (
                    "Test NFC-uitlezing op iOS-toestellen",
                    None, "open", "hoog", date(2026, 3, 10),
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
            p_kaya,
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
            p_nguyen,
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
            p_nguyen,
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
            p_kaya,
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
            p_smit,
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
            p_linden,
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
            p_achterberg,
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
            p_visser,
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
            p_visser,
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
            p_dejong,
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
            p_bakker,
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
            p_dejong,
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
            p_dejong,
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
            p_bakker,
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
            p_kumar,
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
            p_kumar,
            "open",
            "normaal",
            date(2026, 6, 1),
        ),
        (
            bk_ibds,
            "IBDS voortgangsrapportage Tweede Kamer",
            "Stel de halfjaarlijkse voortgangsrapportage IBDS op voor de Tweede Kamer.",
            p_kumar,
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
            p_devries,
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
            p_devries,
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
            p_devries,
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
            p_deblaauw,
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
            p_smit,
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
            p_berg,
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
            p_berg,
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
            p_smit,
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
            p_vermeer,
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
            p_linden,
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
            p_jansen,
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
            p_peeters,
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
            p_devries,
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
            p_hendriks,
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
            p_hendriks,
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
            p_beentjes,
            "in_progress",
            "kritiek",
            date(2026, 2, 14),
        ),
        (
            pi_verzamelbrief_q4,
            "Verzamelbrief Digitalisering Q1 2026 opstellen",
            "Coördineer de bijdragen van alle directies voor de verzamelbrief Q1 2026.",
            p_linden,
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
            p_dgdoo,
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
            p_rutjens,
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
            p_dgdoo,
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
            p_beentjes,
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
    ]

    subtask_count = 0
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
                organisatie_eenheid_id=(
                    org_eenheid.id if org_eenheid else None
                ),
            )
        )

        for sub in subtasks:
            sub_title, sub_assignee, sub_status, sub_prio, sub_dl = sub
            await task_repo.create(
                TaskCreate(
                    title=sub_title,
                    node_id=node.id,
                    assignee_id=(
                        sub_assignee.id if sub_assignee else None
                    ),
                    status=sub_status,
                    priority=sub_prio,
                    deadline=sub_dl,
                    parent_id=parent.id,
                    organisatie_eenheid_id=(
                        org_eenheid.id if org_eenheid else None
                    ),
                )
            )
            subtask_count += 1

    print(
        f"  Taken: {len(tasks_data)} taken + "
        f"{subtask_count} subtaken aangemaakt"
    )

    # =========================================================================
    # 7. NODE STAKEHOLDERS
    # =========================================================================
    from bouwmeester.models.node_stakeholder import NodeStakeholder

    stakeholders_data = [
        # Directeuren als eigenaar van koepeldossiers
        (dos_digi_overheid, p_vermeer, "eigenaar"),
        (dos_digi_samenleving, p_beentjes, "eigenaar"),
        (dos_cio_rijk, p_deblaauw, "eigenaar"),
        (dos_ai, p_beentjes, "eigenaar"),
        (dos_data, p_kewal, "eigenaar"),
        # DigiD / Identiteit
        (maatr_digid_upgrade, p_nguyen, "betrokken"),
        (maatr_digid_upgrade, p_kaya, "betrokken"),
        (maatr_digid_upgrade, p_vanwissen, "eigenaar"),
        (instr_digid, p_tl_digid, "eigenaar"),
        (instr_digid, p_nguyen, "betrokken"),
        (doel_digid_nieuw, p_vanwissen, "eigenaar"),
        (doel_digid_nieuw, p_kaya, "adviseur"),
        # EUDIW
        (instr_eidas_wallet, p_tl_eudiw, "eigenaar"),
        (instr_eidas_wallet, p_kaya, "betrokken"),
        (doel_eudiw, p_tl_eudiw, "eigenaar"),
        # WDO
        (bk_wdo, p_linden, "eigenaar"),
        (maatr_wdo_transitie, p_linden, "eigenaar"),
        (maatr_wdo_transitie, p_achterberg, "adviseur"),
        # MijnOverheid
        (instr_mijnoverheid, p_tl_mijnov, "eigenaar"),
        (instr_mijnoverheid, p_visser, "betrokken"),
        # AI en Algoritmen
        (bk_ai_act, p_dejong, "eigenaar"),
        (bk_ai_act, p_tl_aiact, "betrokken"),
        (instr_algo_register, p_bakker, "eigenaar"),
        (maatr_algo_verpl, p_dejong, "eigenaar"),
        (bk_algo_kader, p_dejong, "betrokken"),
        (bk_algo_kader, p_tl_algo, "eigenaar"),
        (maatr_genai, p_bakker, "betrokken"),
        (dos_ai, p_dejong, "betrokken"),
        # Data
        (bk_ibds, p_kumar, "eigenaar"),
        (doel_fed_data, p_kumar, "eigenaar"),
        (maatr_data_spaces, p_kumar, "betrokken"),
        (dos_data, p_tl_data, "betrokken"),
        # Cloud / CIO
        (bk_cloudbeleid, p_devries, "eigenaar"),
        (maatr_cloud_exit, p_devries, "eigenaar"),
        (bk_cio_stelsel, p_deblaauw, "eigenaar"),
        (bk_cio_stelsel, p_tl_ciostel, "betrokken"),
        (instr_cio_overleg, p_smit, "betrokken"),
        (instr_nora, p_smit, "eigenaar"),
        (maatr_genai, p_devries, "adviseur"),
        # Informatiebeveiliging
        (instr_bio, p_berg, "eigenaar"),
        (instr_bio, p_tl_bio, "betrokken"),
        (doel_bio_compliance, p_berg, "eigenaar"),
        (doel_bio_compliance, p_timmermans, "eigenaar"),
        # NDD
        (instr_ndd, p_vermeer, "eigenaar"),
        (instr_ndd, p_linden, "betrokken"),
        # Vendor reductie
        (maatr_it_inhuur, p_jansen, "eigenaar"),
        (doel_vendor_reductie, p_peeters, "betrokken"),
        (doel_vendor_reductie, p_jansen, "betrokken"),
        # NDS breed
        (bk_nds, p_dgdoo, "eigenaar"),
        (bk_nds, p_vermeer, "betrokken"),
        (bk_nds, p_beentjes, "betrokken"),
        (bk_nds, p_deblaauw, "betrokken"),
        # Inclusie
        (doel_inclusie, p_hendriks, "eigenaar"),
        (doel_inclusie, p_tl_incl, "betrokken"),
        # Open Overheid
        (dos_digi_overheid, p_rutjens, "betrokken"),
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

    await db.commit()
    print("\nSeed voltooid!")


async def main() -> None:
    async with async_session() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
