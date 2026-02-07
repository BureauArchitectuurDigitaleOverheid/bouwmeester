"""Seed script for Bouwmeester – populates the database with example policy corpus data.

Run with:
    python -m bouwmeester.seed
"""

import asyncio
import uuid
from datetime import date

from sqlalchemy import select

from bouwmeester.core.database import async_session, engine
from bouwmeester.models import (  # noqa: F401 – ensure metadata is populated
    Beleidskader,
    CorpusNode,
    Doel,
    Dossier,
    Edge,
    EdgeType,
    Instrument,
    Maatregel,
    NodeStakeholder,
    Person,
    PolitiekeInput,
    Task,
)


async def seed() -> None:
    # ------------------------------------------------------------------
    # 0. Check whether seed data already exists
    # ------------------------------------------------------------------
    async with async_session() as session:
        result = await session.execute(select(EdgeType).limit(1))
        if result.scalars().first() is not None:
            print("Seed data already present – skipping.")
            return

    # ------------------------------------------------------------------
    # 1. Edge types
    # ------------------------------------------------------------------
    print("Seeding edge types ...")
    edge_types = [
        EdgeType(
            id="kadert",
            label_nl="Kadert in",
            label_en="Is framed by",
            description="Een node opereert binnen het kader van een andere node.",
        ),
        EdgeType(
            id="draagt_bij_aan",
            label_nl="Draagt bij aan",
            label_en="Contributes to",
            description="Een node draagt bij aan het bereiken van een andere node.",
        ),
        EdgeType(
            id="implementeert",
            label_nl="Implementeert",
            label_en="Implements",
            description="Een node implementeert een andere node.",
        ),
        EdgeType(
            id="conflicteert_met",
            label_nl="Conflicteert met",
            label_en="Conflicts with",
            description="Twee nodes staan op gespannen voet met elkaar.",
        ),
        EdgeType(
            id="vervangt",
            label_nl="Vervangt",
            label_en="Replaces",
            description="Een node vervangt een andere node.",
        ),
        EdgeType(
            id="vereist",
            label_nl="Vereist",
            label_en="Requires",
            description="Een node is afhankelijk van een andere node.",
        ),
        EdgeType(
            id="aanvulling_op",
            label_nl="Aanvulling op",
            label_en="Supplements",
            description="Een node vult een andere node aan.",
        ),
    ]

    async with async_session() as session:
        session.add_all(edge_types)
        await session.commit()
    print(f"  -> {len(edge_types)} edge types created.")

    # ------------------------------------------------------------------
    # 2. Corpus nodes + type-specific records
    # ------------------------------------------------------------------
    print("Seeding corpus nodes ...")

    # Pre-generate UUIDs so we can reference them in edges / tasks later.
    ids: dict[str, uuid.UUID] = {
        "eu_digitale_strategie": uuid.uuid4(),
        "nl_digitaliseringsstrategie": uuid.uuid4(),
        "doel_100_digitaal": uuid.uuid4(),
        "doel_digitale_inclusie": uuid.uuid4(),
        "doel_open_source": uuid.uuid4(),
        "dossier_basisregistraties": uuid.uuid4(),
        "dossier_ai_rijksoverheid": uuid.uuid4(),
        "dossier_wdo": uuid.uuid4(),
        "instrument_wdo": uuid.uuid4(),
        "instrument_innovatiebudget": uuid.uuid4(),
        "instrument_algoritmeregister": uuid.uuid4(),
        "maatregel_eid": uuid.uuid4(),
        "maatregel_ai_toezicht": uuid.uuid4(),
        "pi_coalitieakkoord": uuid.uuid4(),
        "pi_motie_dekker": uuid.uuid4(),
        "pi_kamerbrief": uuid.uuid4(),
    }

    # --- CorpusNode rows (parent table) ---------------------------------
    corpus_nodes = [
        # Beleidskaders
        CorpusNode(
            id=ids["eu_digitale_strategie"],
            node_type="beleidskader",
            title="Europese Digitale Strategie 2030",
            description=(
                "Het Europese beleidskader voor de digitale transformatie van "
                "lidstaten richting 2030, inclusief digitale vaardigheden, "
                "infrastructuur en e-government."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["nl_digitaliseringsstrategie"],
            node_type="beleidskader",
            title="Nederlandse Digitaliseringsstrategie",
            description=(
                "De nationale strategie voor digitalisering van de overheid, "
                "economie en samenleving, in lijn met Europese ambities."
            ),
            status="actief",
        ),
        # Doelen
        CorpusNode(
            id=ids["doel_100_digitaal"],
            node_type="doel",
            title="100% digitale overheidsdiensten in 2030",
            description=(
                "Alle overheidsdiensten zijn uiterlijk in 2030 volledig "
                "digitaal beschikbaar voor burgers en bedrijven."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["doel_digitale_inclusie"],
            node_type="doel",
            title="Digitale inclusie voor alle burgers",
            description=(
                "Iedere burger kan digitaal meedoen; er is aandacht voor "
                "toegankelijkheid, digitale vaardigheden en ondersteuning."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["doel_open_source"],
            node_type="doel",
            title="Open source bij de overheid",
            description=(
                "De overheid maakt software-ontwikkeling zoveel mogelijk open "
                "source beschikbaar en herbruikbaar."
            ),
            status="actief",
        ),
        # Dossiers
        CorpusNode(
            id=ids["dossier_basisregistraties"],
            node_type="dossier",
            title="Modernisering Basisregistraties",
            description=(
                "Programma om de basisregistraties (BRP, BAG, BRK, etc.) te "
                "moderniseren en beter op elkaar te laten aansluiten."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["dossier_ai_rijksoverheid"],
            node_type="dossier",
            title="AI bij de Rijksoverheid",
            description=(
                "Verkenning en beleidsontwikkeling rond verantwoord gebruik "
                "van artifici\u00eble intelligentie binnen de Rijksoverheid."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["dossier_wdo"],
            node_type="dossier",
            title="Wet Digitale Overheid (WDO)",
            description=(
                "Het wetstraject voor de Wet Digitale Overheid, gericht op "
                "het wettelijk kader voor digitale overheidsdienstverlening."
            ),
            status="actief",
        ),
        # Instrumenten
        CorpusNode(
            id=ids["instrument_wdo"],
            node_type="instrument",
            title="Wet Digitale Overheid",
            description=(
                "De Wet Digitale Overheid regelt eisen voor digitale "
                "dienstverlening, identificatie en informatiebeveiliging."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["instrument_innovatiebudget"],
            node_type="instrument",
            title="Innovatiebudget Digitale Overheid",
            description=(
                "Subsidie-instrument waarmee innovatieve digitaliseringsprojecten "
                "bij de overheid worden gefinancierd."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["instrument_algoritmeregister"],
            node_type="instrument",
            title="Algoritmeregister",
            description=(
                "Publiek register waarin de overheid transparant maakt welke "
                "algoritmes zij gebruikt en met welk doel."
            ),
            status="actief",
        ),
        # Maatregelen
        CorpusNode(
            id=ids["maatregel_eid"],
            node_type="maatregel",
            title="Implementatie eID-stelsel",
            description=(
                "Landelijke invoering van het elektronisch identificatiestelsel "
                "voor veilige toegang tot overheidsdiensten."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["maatregel_ai_toezicht"],
            node_type="maatregel",
            title="Oprichting AI-toezichtsorgaan",
            description=(
                "Oprichting van een onafhankelijk orgaan dat toezicht houdt "
                "op het gebruik van AI door de overheid."
            ),
            status="actief",
        ),
        # Politieke input
        CorpusNode(
            id=ids["pi_coalitieakkoord"],
            node_type="politieke_input",
            title="Coalitieakkoord 2024 - Digitale Overheid",
            description=(
                "Passage uit het coalitieakkoord 2024 over de ambities "
                "rondom digitale overheidsdienstverlening."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["pi_motie_dekker"],
            node_type="politieke_input",
            title="Motie-Dekker inzake open source",
            description=(
                "Motie die de regering verzoekt om open source als norm te "
                "hanteren bij overheids-ICT-projecten."
            ),
            status="actief",
        ),
        CorpusNode(
            id=ids["pi_kamerbrief"],
            node_type="politieke_input",
            title="Kamerbrief voortgang digitalisering",
            description=(
                "Periodieke Kamerbrief over de voortgang van het "
                "digitaliseringsprogramma bij de Rijksoverheid."
            ),
            status="actief",
        ),
    ]

    async with async_session() as session:
        session.add_all(corpus_nodes)
        await session.commit()
    print(f"  -> {len(corpus_nodes)} corpus nodes created.")

    # --- Type-specific child rows ----------------------------------------
    print("Seeding type-specific records ...")

    beleidskaders = [
        Beleidskader(
            id=ids["eu_digitale_strategie"],
            scope="eu",
            geldig_van=date(2024, 1, 1),
        ),
        Beleidskader(
            id=ids["nl_digitaliseringsstrategie"],
            scope="nationaal",
            geldig_van=date(2023, 6, 1),
        ),
    ]

    doelen = [
        Doel(
            id=ids["doel_100_digitaal"],
            type="politiek",
            meetbaar=True,
            streefwaarde="100% digitaal",
        ),
        Doel(
            id=ids["doel_digitale_inclusie"],
            type="organisatorisch",
            meetbaar=True,
        ),
        Doel(
            id=ids["doel_open_source"],
            type="operationeel",
            meetbaar=False,
        ),
    ]

    dossiers = [
        Dossier(
            id=ids["dossier_basisregistraties"],
            fase="beleidsvorming",
            prioriteit="hoog",
        ),
        Dossier(
            id=ids["dossier_ai_rijksoverheid"],
            fase="verkenning",
            prioriteit="kritiek",
        ),
        Dossier(
            id=ids["dossier_wdo"],
            fase="uitvoering",
            prioriteit="hoog",
        ),
    ]

    instrumenten = [
        Instrument(
            id=ids["instrument_wdo"],
            type="wetgeving",
        ),
        Instrument(
            id=ids["instrument_innovatiebudget"],
            type="subsidie",
        ),
        Instrument(
            id=ids["instrument_algoritmeregister"],
            type="voorlichting",
        ),
    ]

    maatregelen = [
        Maatregel(
            id=ids["maatregel_eid"],
            uitvoerder="RvIG",
            kosten_indicatie="\u20ac50M",
        ),
        Maatregel(
            id=ids["maatregel_ai_toezicht"],
            uitvoerder="MinBZK",
        ),
    ]

    politieke_inputs = [
        PolitiekeInput(
            id=ids["pi_coalitieakkoord"],
            type="coalitieakkoord",
            datum=date(2024, 1, 15),
        ),
        PolitiekeInput(
            id=ids["pi_motie_dekker"],
            type="motie",
            referentie="36xxx-42",
            status="in_behandeling",
        ),
        PolitiekeInput(
            id=ids["pi_kamerbrief"],
            type="kamerbrief",
            datum=date(2024, 9, 15),
        ),
    ]

    async with async_session() as session:
        session.add_all(beleidskaders)
        session.add_all(doelen)
        session.add_all(dossiers)
        session.add_all(instrumenten)
        session.add_all(maatregelen)
        session.add_all(politieke_inputs)
        await session.commit()
    print("  -> type-specific records created.")

    # ------------------------------------------------------------------
    # 3. Edges (relationships)
    # ------------------------------------------------------------------
    print("Seeding edges ...")

    edges = [
        # NL Digitaliseringsstrategie kadert in EU Digitale Strategie
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["nl_digitaliseringsstrategie"],
            to_node_id=ids["eu_digitale_strategie"],
            edge_type_id="kadert",
            description="De Nederlandse strategie opereert binnen het Europese kader.",
        ),
        # 100% digitaal draagt bij aan EU Digitale Strategie
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["doel_100_digitaal"],
            to_node_id=ids["eu_digitale_strategie"],
            edge_type_id="draagt_bij_aan",
            description=(
                "Volledig digitale dienstverlening draagt bij"
                " aan de Europese doelen."
            ),
        ),
        # Digitale inclusie draagt bij aan NL Digitaliseringsstrategie
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["doel_digitale_inclusie"],
            to_node_id=ids["nl_digitaliseringsstrategie"],
            edge_type_id="draagt_bij_aan",
            description="Inclusie is een kernonderdeel van de nationale strategie.",
        ),
        # Modernisering Basisregistraties implementeert 100% digitaal
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["dossier_basisregistraties"],
            to_node_id=ids["doel_100_digitaal"],
            edge_type_id="implementeert",
            description=(
                "Moderne basisregistraties zijn voorwaarde"
                " voor volledig digitale diensten."
            ),
        ),
        # AI bij Rijksoverheid kadert in NL Digitaliseringsstrategie
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["dossier_ai_rijksoverheid"],
            to_node_id=ids["nl_digitaliseringsstrategie"],
            edge_type_id="kadert",
            description="AI-beleid valt binnen de bredere digitaliseringsstrategie.",
        ),
        # WDO (dossier) implementeert NL Digitaliseringsstrategie
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["dossier_wdo"],
            to_node_id=ids["nl_digitaliseringsstrategie"],
            edge_type_id="implementeert",
            description=(
                "De WDO geeft wettelijke invulling"
                " aan de digitaliseringsstrategie."
            ),
        ),
        # Wet Digitale Overheid (instrument) implementeert WDO (dossier)
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["instrument_wdo"],
            to_node_id=ids["dossier_wdo"],
            edge_type_id="implementeert",
            description="Het wetsinstrument implementeert het beleidsdossier.",
        ),
        # Innovatiebudget draagt bij aan Open source
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["instrument_innovatiebudget"],
            to_node_id=ids["doel_open_source"],
            edge_type_id="draagt_bij_aan",
            description="Het innovatiebudget financiert open source-initiatieven.",
        ),
        # Algoritmeregister draagt bij aan AI bij Rijksoverheid
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["instrument_algoritmeregister"],
            to_node_id=ids["dossier_ai_rijksoverheid"],
            edge_type_id="draagt_bij_aan",
            description="Het algoritmeregister ondersteunt transparant AI-gebruik.",
        ),
        # eID-stelsel implementeert Wet Digitale Overheid (instrument)
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["maatregel_eid"],
            to_node_id=ids["instrument_wdo"],
            edge_type_id="implementeert",
            description="Het eID-stelsel is de concrete uitvoering van de WDO-eisen.",
        ),
        # AI-toezichtsorgaan kadert in AI bij Rijksoverheid
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["maatregel_ai_toezicht"],
            to_node_id=ids["dossier_ai_rijksoverheid"],
            edge_type_id="kadert",
            description="Het toezichtsorgaan opereert binnen het AI-beleid.",
        ),
        # Coalitieakkoord draagt bij aan 100% digitaal
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["pi_coalitieakkoord"],
            to_node_id=ids["doel_100_digitaal"],
            edge_type_id="draagt_bij_aan",
            description=(
                "Het coalitieakkoord bevat ambities"
                " voor digitale dienstverlening."
            ),
        ),
        # Motie-Dekker draagt bij aan Open source
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["pi_motie_dekker"],
            to_node_id=ids["doel_open_source"],
            edge_type_id="draagt_bij_aan",
            description=(
                "De motie verzoekt de regering open source"
                " als norm te hanteren."
            ),
        ),
        # Kamerbrief kadert in Modernisering Basisregistraties
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["pi_kamerbrief"],
            to_node_id=ids["dossier_basisregistraties"],
            edge_type_id="kadert",
            description=(
                "De Kamerbrief rapporteert over de voortgang"
                " van het programma."
            ),
        ),
        # Open source conflicteert met Innovatiebudget (budget tension)
        Edge(
            id=uuid.uuid4(),
            from_node_id=ids["doel_open_source"],
            to_node_id=ids["instrument_innovatiebudget"],
            edge_type_id="conflicteert_met",
            description=(
                "Spanning rond budgetprioritering: open source-eisen kunnen "
                "botsen met de bestedingscriteria van het innovatiebudget."
            ),
        ),
    ]

    async with async_session() as session:
        session.add_all(edges)
        await session.commit()
    print(f"  -> {len(edges)} edges created.")

    # ------------------------------------------------------------------
    # 4. People
    # ------------------------------------------------------------------
    print("Seeding people ...")

    person_ids: dict[str, uuid.UUID] = {
        "jan": uuid.uuid4(),
        "maria": uuid.uuid4(),
        "pieter": uuid.uuid4(),
    }

    people = [
        Person(
            id=person_ids["jan"],
            naam="Jan de Vries",
            email="jan@minbzk.nl",
            afdeling="Digitale Overheid",
            functie="Beleidsmedewerker",
        ),
        Person(
            id=person_ids["maria"],
            naam="Maria van den Berg",
            email="maria@minbzk.nl",
            afdeling="Digitale Overheid",
            functie="Senior beleidsadviseur",
        ),
        Person(
            id=person_ids["pieter"],
            naam="Pieter Bakker",
            email="pieter@minbzk.nl",
            afdeling="CIO Rijk",
            functie="Programmamanager",
        ),
    ]

    async with async_session() as session:
        session.add_all(people)
        await session.commit()
    print(f"  -> {len(people)} people created.")

    # ------------------------------------------------------------------
    # 5. Tasks
    # ------------------------------------------------------------------
    print("Seeding tasks ...")

    tasks = [
        Task(
            id=uuid.uuid4(),
            node_id=ids["dossier_ai_rijksoverheid"],
            title="Beleidsnotitie AI-kader schrijven",
            description=(
                "Stel een beleidsnotitie op met het kader voor verantwoord "
                "AI-gebruik bij de Rijksoverheid."
            ),
            assignee_id=person_ids["jan"],
            priority="hoog",
            deadline=date(2025, 3, 15),
            status="open",
        ),
        Task(
            id=uuid.uuid4(),
            node_id=ids["dossier_basisregistraties"],
            title="Stakeholderanalyse basisregistraties",
            description=(
                "Breng alle betrokken stakeholders in kaart voor het "
                "moderniseringsprogramma basisregistraties."
            ),
            assignee_id=person_ids["maria"],
            priority="normaal",
            deadline=date(2025, 2, 28),
            status="open",
        ),
        Task(
            id=uuid.uuid4(),
            node_id=ids["pi_motie_dekker"],
            title="Reactie op motie-Dekker voorbereiden",
            description=(
                "Bereid een ambtelijke reactie voor op de motie-Dekker "
                "over open source bij de overheid."
            ),
            assignee_id=person_ids["pieter"],
            priority="hoog",
            deadline=date(2025, 2, 15),
            status="in_progress",
        ),
        Task(
            id=uuid.uuid4(),
            node_id=ids["dossier_wdo"],
            title="Voortgangsrapportage WDO Q1",
            description=(
                "Stel de kwartaalrapportage Q1 op over de voortgang "
                "van de Wet Digitale Overheid."
            ),
            assignee_id=None,
            priority="normaal",
            deadline=date(2025, 3, 31),
            status="open",
        ),
    ]

    async with async_session() as session:
        session.add_all(tasks)
        await session.commit()
    print(f"  -> {len(tasks)} tasks created.")

    # ------------------------------------------------------------------
    # 6. Node stakeholders
    # ------------------------------------------------------------------
    print("Seeding node stakeholders ...")

    stakeholders = [
        # Jan is eigenaar of "AI bij de Rijksoverheid"
        NodeStakeholder(
            id=uuid.uuid4(),
            node_id=ids["dossier_ai_rijksoverheid"],
            person_id=person_ids["jan"],
            rol="eigenaar",
        ),
        # Maria is eigenaar of "Modernisering Basisregistraties"
        NodeStakeholder(
            id=uuid.uuid4(),
            node_id=ids["dossier_basisregistraties"],
            person_id=person_ids["maria"],
            rol="eigenaar",
        ),
        # Pieter is betrokken at "Wet Digitale Overheid (WDO)"
        NodeStakeholder(
            id=uuid.uuid4(),
            node_id=ids["dossier_wdo"],
            person_id=person_ids["pieter"],
            rol="betrokken",
        ),
        # Jan is betrokken at "Algoritmeregister"
        NodeStakeholder(
            id=uuid.uuid4(),
            node_id=ids["instrument_algoritmeregister"],
            person_id=person_ids["jan"],
            rol="betrokken",
        ),
        # Maria is adviseur at "AI bij de Rijksoverheid"
        NodeStakeholder(
            id=uuid.uuid4(),
            node_id=ids["dossier_ai_rijksoverheid"],
            person_id=person_ids["maria"],
            rol="adviseur",
        ),
    ]

    async with async_session() as session:
        session.add_all(stakeholders)
        await session.commit()
    print(f"  -> {len(stakeholders)} node stakeholders created.")

    # ------------------------------------------------------------------
    print("\nSeed complete!")


async def main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
