"""Shared prompt templates for BZK policy domain (Dutch)."""

import json

# Maximum number of tags to include in prompts to control token usage.
MAX_TAGS_IN_PROMPT = 200
MAX_TEXT_IN_PROMPT = 10000
MAX_DESCRIPTION_IN_PROMPT = 500

_TYPE_LABELS: dict[str, str] = {
    "motie": "aangenomen motie",
    "kamervraag": "schriftelijke kamervraag",
    "toezegging": "toezegging",
    "amendement": "amendement",
    "commissiedebat": "commissiedebat",
}

_NODE_TYPE_LABELS: dict[str, str] = {
    "dossier": "beleidsdossier",
    "doel": "beleidsdoel",
    "instrument": "beleidsinstrument",
    "beleidskader": "beleidskader",
    "maatregel": "beleidsmaatregel",
    "politieke_input": "politieke input",
    "probleem": "beleidsprobleem",
    "effect": "beleidseffect",
    "beleidsoptie": "beleidsoptie",
    "bron": "bron",
    "notitie": "notitie",
    "overig": "node",
}


def build_extract_tags_prompt(
    titel: str,
    onderwerp: str,
    document_tekst: str | None,
    bestaande_tags: list[str],
    context_hint: str = "motie",
) -> str:
    type_label = _TYPE_LABELS.get(context_hint, context_hint)
    item_content = f"TITEL: {titel}\nONDERWERP: {onderwerp}"
    if document_tekst:
        item_content += f"\n\nDOCUMENTTEKST:\n{document_tekst[:MAX_TEXT_IN_PROMPT]}"

    tags_json = json.dumps(bestaande_tags[:MAX_TAGS_IN_PROMPT], ensure_ascii=False)
    return (
        "Je bent een beleidsanalist van het ministerie van BZK"
        " (Binnenlandse Zaken en Koninkrijksrelaties)."
        f" Analyseer deze {type_label} en bepaal welke"
        " beleidstags relevant zijn.\n\n"
        f"{type_label.upper()}:\n{item_content}\n\n"
        f"BESTAANDE TAGS IN HET SYSTEEM:\n{tags_json}\n\n"
        "Instructies:\n"
        "- Selecteer ALLEEN tags die specifiek relevant"
        f" zijn voor deze {type_label}\n"
        "- Vermijd te brede/generieke tags. Tags als"
        ' "overheid", "data", "digitalisering" op zichzelf'
        " zijn te breed — gebruik altijd de meest specifieke"
        " subtag (bijv."
        ' "digitalisering/AI/generatieve-AI"'
        ' in plaats van "digitalisering")\n'
        "- Selecteer een brede parent-tag ALLEEN als de"
        f" {type_label} echt over het hele brede onderwerp gaat\n"
        "- Stel maximaal 3 nieuwe tags voor als de"
        " bestaande tags het onderwerp niet dekken\n"
        "- Nieuwe tags moeten het hiërarchische"
        " pad-formaat volgen"
        ' (bijv. "digitalisering/AI/privacy")\n'
        "- Geef een korte samenvatting (max 2 zinnen)"
        f" van wat de {type_label} vraagt en waarom\n\n"
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "samenvatting": "...",\n'
        '  "matched_tags": ["specifieke/tag1",'
        ' "specifieke/tag2"],\n'
        '  "suggested_new_tags":'
        ' ["nieuwe/specifieke/tag"]\n'
        "}"
    )


def build_suggest_tags_prompt(
    title: str,
    description: str | None,
    node_type: str,
    bestaande_tags: list[str],
) -> str:
    type_label = _NODE_TYPE_LABELS.get(node_type, node_type)
    content = f"TITEL: {title}"
    if description:
        content += f"\nBESCHRIJVING:\n{description[:MAX_TEXT_IN_PROMPT]}"

    tags_json = json.dumps(bestaande_tags[:MAX_TAGS_IN_PROMPT], ensure_ascii=False)
    return (
        "Je bent een beleidsanalist van het ministerie van BZK"
        " (Binnenlandse Zaken en Koninkrijksrelaties)."
        f" Analyseer dit {type_label} en bepaal welke"
        " beleidstags relevant zijn.\n\n"
        f"{type_label.upper()}:\n{content}\n\n"
        f"BESTAANDE TAGS IN HET SYSTEEM:\n{tags_json}\n\n"
        "Instructies:\n"
        "- Selecteer ALLEEN tags die specifiek relevant"
        f" zijn voor dit {type_label}\n"
        "- Vermijd te brede/generieke tags — gebruik de"
        " meest specifieke subtag\n"
        "- Stel maximaal 3 nieuwe tags voor als de"
        " bestaande tags het onderwerp niet dekken\n"
        "- Nieuwe tags moeten het hiërarchische"
        " pad-formaat volgen"
        ' (bijv. "digitalisering/AI/privacy")\n\n'
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "matched_tags": ["specifieke/tag1",'
        ' "specifieke/tag2"],\n'
        '  "suggested_new_tags":'
        ' ["nieuwe/specifieke/tag"]\n'
        "}"
    )


def build_edge_relevance_prompt(
    source_title: str,
    source_description: str | None,
    target_title: str,
    target_description: str | None,
) -> str:
    source = f"TITEL: {source_title}"
    if source_description:
        source += f"\nBESCHRIJVING: {source_description[:MAX_DESCRIPTION_IN_PROMPT]}"

    target = f"TITEL: {target_title}"
    if target_description:
        target += f"\nBESCHRIJVING: {target_description[:MAX_DESCRIPTION_IN_PROMPT]}"

    return (
        "Je bent een beleidsanalist van het ministerie van BZK."
        " Beoordeel of er een inhoudelijke relatie bestaat"
        " tussen deze twee beleidsnodes.\n\n"
        f"NODE A:\n{source}\n\n"
        f"NODE B:\n{target}\n\n"
        "Instructies:\n"
        "- Geef een score van 0.0 (geen relatie) tot"
        " 1.0 (sterk gerelateerd)\n"
        "- Stel een relatietype voor uit:"
        " implementeert, draagt_bij_aan, vloeit_voort_uit,"
        " conflicteert_met, verwijst_naar, vereist,"
        " evalueert, vervangt, onderdeel_van,"
        " leidt_tot, adresseert, meet\n"
        "- Geef een korte reden in het Nederlands\n\n"
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "score": 0.8,\n'
        '  "suggested_edge_type": "draagt_bij_aan",\n'
        '  "reason": "Beide nodes gaan over ..."\n'
        "}"
    )


def build_gap_analysis_prompt(
    dossier_title: str,
    dossier_description: str | None,
    gaps: list[dict],
) -> str:
    content = f"DOSSIER: {dossier_title}"
    if dossier_description:
        content += f"\nBESCHRIJVING: {dossier_description[:MAX_DESCRIPTION_IN_PROMPT]}"

    gaps_text = json.dumps(gaps, ensure_ascii=False, indent=2)

    return (
        "Je bent een beleidsanalist van het ministerie van BZK."
        " Analyseer de volledigheid van het volgende beleidsdossier"
        " op basis van het Beleidskompas-model.\n\n"
        f"{content}\n\n"
        f"GEVONDEN LACUNES:\n{gaps_text}\n\n"
        "Instructies:\n"
        "- Geef een korte narratieve samenvatting (max 3 zinnen)"
        " van de huidige stand van het dossier\n"
        "- Geef concrete aanbevelingen (max 5) voor de"
        " belangrijkste vervolgstappen\n"
        "- Schrijf alles in het Nederlands\n\n"
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "narrative": "Samenvatting van de volledigheid...",\n'
        '  "recommendations": ["Aanbeveling 1", "Aanbeveling 2"]\n'
        "}"
    )


def build_kompas_relevance_prompt(
    dossier_title: str,
    step_description: str,
    candidate_title: str,
    candidate_description: str | None,
) -> str:
    candidate = f"TITEL: {candidate_title}"
    if candidate_description:
        candidate += (
            f"\nBESCHRIJVING: {candidate_description[:MAX_DESCRIPTION_IN_PROMPT]}"
        )

    return (
        "Je bent een beleidsanalist van het ministerie van BZK."
        " Beoordeel of de volgende node relevant is om te koppelen"
        " aan een beleidsdossier voor een specifieke"
        " Beleidskompas-stap.\n\n"
        f"DOSSIER: {dossier_title}\n"
        f"BELEIDSKOMPAS-STAP: {step_description}\n\n"
        f"KANDIDAAT-NODE:\n{candidate}\n\n"
        "Instructies:\n"
        "- Geef een score van 0.0 (niet relevant) tot"
        " 1.0 (zeer relevant)\n"
        "- Stel een relatietype voor uit:"
        " implementeert, draagt_bij_aan, vloeit_voort_uit,"
        " verwijst_naar, onderdeel_van, adresseert, meet\n"
        "- Geef een korte reden in het Nederlands\n\n"
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "score": 0.8,\n'
        '  "suggested_edge_type": "onderdeel_van",\n'
        '  "reason": "Deze node is relevant omdat..."\n'
        "}"
    )


def build_lead_intake_prompt(
    raw_text: str, existing_tags: list[str] | None = None
) -> str:
    """Build a prompt to parse raw intake text into structured lead data."""
    from datetime import date

    today = date.today().isoformat()
    tags_hint = ""
    if existing_tags:
        tags_json = json.dumps(existing_tags[:MAX_TAGS_IN_PROMPT], ensure_ascii=False)
        tags_hint = f"\n\nBESCHIKBARE TAGS (gebruik deze bij voorkeur):\n{tags_json}\n"
    return (
        "Je bent een medewerker van team Regelrecht bij het ministerie van BZK."
        " Je beheert een sales funnel van leads: organisaties en mensen die"
        " interesse hebben in Regelrecht of Rules as Code.\n\n"
        " Analyseer de volgende intake (tekst of screenshot van een e-mail/"
        "bericht) en extraheer de relevante informatie voor een nieuwe lead.\n\n"
        f"INTAKE:\n{raw_text[:MAX_TEXT_IN_PROMPT]}\n\n"
        "Instructies:\n"
        "- De titel moet de naam van de organisatie of afdeling zijn die"
        " contact opneemt (bijv. 'CDO Office MinJenV' of 'Gemeente Nijmegen')."
        " NIET de actie of het onderwerp.\n"
        "- De organisatie is de volledige naam van de organisatie\n"
        "- Maak een beknopte beschrijving van wat ze willen\n"
        "- Extraheer de naam van de contactpersoon als die wordt genoemd\n"
        "- Extraheer het e-mailadres van de contactpersoon als dat wordt genoemd\n"
        "- Extraheer het telefoonnummer van de contactpersoon als dat wordt genoemd\n"
        f"- Vandaag is {today}. Extraheer ALLEEN de verzenddatum van het"
        " bericht/e-mail zelf (de datum in de header, of 'gisteren',"
        " 'vorige week'). NIET datums die in de inhoud worden genoemd"
        " (zoals 'vorig jaar november'). Geef als ISO-formaat (YYYY-MM-DD)."
        " Als de verzenddatum niet duidelijk zichtbaar is, geef null.\n"
        "- Als het bericht gericht is aan iemand"
        " (bijv. 'Hoi Anne' of 'Aan: Schuth, Anne'),"
        " extraheer dan de voornaam van de ontvanger."
        " Dit is de persoon via wie de lead binnenkwam.\n"
        "- Stel maximaal 5 relevante tags voor."
        " Gebruik bestaande tags als ze relevant zijn."
        " Verzin gerust nieuwe korte tags als dat beter past"
        " (bijv. 'rules-as-code', 'belastingdienst', 'poc').\n" + tags_hint + "\n"
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "title": "Naam organisatie/afdeling",\n'
        '  "organization": "Volledige naam organisatie",\n'
        '  "description": "Beschrijving van de vraag/behoefte",\n'
        '  "contact_name": "Naam contactpersoon",\n'
        '  "contact_email": "email@example.nl of null",\n'
        '  "contact_phone": "telefoonnummer of null",\n'
        '  "original_date": "YYYY-MM-DD of null",\n'
        '  "suggested_tags": ["tag1", "tag2"],\n'
        '  "addressed_to": "Voornaam van de ontvanger of null"\n'
        "}"
    )


def build_lead_update_prompt(
    raw_text: str,
    lead_context: str,
    initiatief_naam: str | None = None,
) -> str:
    """Build a prompt that turns raw input + lead context into two update versions.

    `lead_context` is a paragraph the route assembles: lead title, organisatie,
    initiatief metadata (naam, beschrijving), recent activities, contact names.
    `initiatief_naam` is also passed separately so subject lines can include
    it without the LLM having to fish it out of the context blob.
    """
    initiatief_label = initiatief_naam or "(initiatief onbekend)"
    return (
        "Je schrijft een update over een lopende lead binnen een initiatief"
        " bij de Nederlandse overheid. De update bestaat uit drie tekstdelen"
        " plus een mail-onderwerp. Schrijf in het Nederlands, zakelijk maar"
        " toegankelijk. Verzin niets dat niet in de context of de ruwe invoer"
        " staat — vraag liever om iets weg te laten dan om het te bedenken.\n\n"
        f"INITIATIEF: {initiatief_label}\n\n"
        f"CONTEXT (lead + initiatief + historie):\n"
        f"{lead_context[:MAX_TEXT_IN_PROMPT]}\n\n"
        f"RUWE INVOER VAN DE GEBRUIKER:\n{raw_text[:MAX_TEXT_IN_PROMPT]}\n\n"
        "Lever vier velden:\n"
        "- titel: korte titel voor de update (max 80 tekens),"
        " bv. 'Pilot gestart met MinJenV'.\n"
        "- body_internal: 2-5 alinea's voor het project-/trajectteam."
        " Mag namen, knelpunten, vervolgafspraken en concrete getallen"
        " bevatten. Markdown toegestaan: alinea's, **vet**, lijsten met '-'.\n"
        "- body_public: 1 tot 3 zinnen voor de publieke community-pagina van"
        " het initiatief. GEEN interne namen, GEEN citaten, GEEN bedragen of"
        " stappen die intern zijn. Wel mag genoemd worden welke organisatie"
        " het betreft en wat het thema is, op hoofdlijnen.\n"
        "- mail_subject: Subject voor de mail aan het team. Begin met de"
        f" naam van het initiatief, bv. '{initiatief_label} — ...'.\n\n"
        "Geef je antwoord als JSON (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "titel": "...",\n'
        '  "body_internal": "...",\n'
        '  "body_public": "...",\n'
        '  "mail_subject": "..."\n'
        "}"
    )


MAX_CANDIDATES_IN_PROMPT = 30


def build_match_opdracht_contacts_prompt(
    opdracht_titel: str,
    opdracht_beschrijving: str | None,
    fcc_contact_fields: dict[str, str],
    fcc_afdeling: str | None,
    kandidaat_personen: list[dict],
    kandidaat_eenheden: list[dict],
) -> str:
    """Build a prompt to match persons and org units to an opdracht."""
    opdracht_info = f"TITEL: {opdracht_titel}"
    if opdracht_beschrijving:
        opdracht_info += (
            f"\nBESCHRIJVING: {opdracht_beschrijving[:MAX_DESCRIPTION_IN_PROMPT]}"
        )
    if fcc_afdeling:
        opdracht_info += f"\nAFDELING: {fcc_afdeling}"

    fcc_text = ""
    if fcc_contact_fields:
        fcc_parts = [f"  {k}: {v}" for k, v in fcc_contact_fields.items() if v]
        if fcc_parts:
            fcc_text = "\nCONTACTVELDEN UIT BRONSYSTEEM:\n" + "\n".join(fcc_parts)

    # Sort candidates: prioritize those whose name appears in contact fields or
    # afdeling, so that truncation (MAX_CANDIDATES_IN_PROMPT) keeps the most
    # relevant candidates rather than relying on arbitrary DB ordering.
    search_terms = [v.lower() for v in fcc_contact_fields.values() if v]
    if fcc_afdeling:
        search_terms.append(fcc_afdeling.lower())

    def _person_relevance(p: dict) -> int:
        naam = p.get("naam", "").lower()
        eenheid = p.get("eenheid", "").lower()
        for term in search_terms:
            if naam in term or term in naam:
                return 0
            if eenheid and (eenheid in term or term in eenheid):
                return 1
        return 2

    def _eenheid_relevance(e: dict) -> int:
        naam = e.get("naam", "").lower()
        for term in search_terms:
            if naam in term or term in naam:
                return 0
        return 1

    sorted_personen = sorted(kandidaat_personen, key=_person_relevance)
    sorted_eenheden = sorted(kandidaat_eenheden, key=_eenheid_relevance)

    personen_json = json.dumps(
        sorted_personen[:MAX_CANDIDATES_IN_PROMPT], ensure_ascii=False
    )
    eenheden_json = json.dumps(
        sorted_eenheden[:MAX_CANDIDATES_IN_PROMPT], ensure_ascii=False
    )

    return (
        "Je bent een medewerker van het ministerie van BZK."
        " Je taak is om te bepalen welke personen en organisatie-eenheden"
        " betrokken zijn bij een opdracht, op basis van de beschikbare"
        " informatie.\n\n"
        f"OPDRACHT:\n{opdracht_info}\n"
        f"{fcc_text}\n\n"
        f"KANDIDAAT-PERSONEN:\n{personen_json}\n\n"
        f"KANDIDAAT-EENHEDEN:\n{eenheden_json}\n\n"
        "Instructies:\n"
        "- Match personen op basis van naamovereenkomst met contactvelden,"
        " of op basis van hun functie/eenheid en de opdracht-inhoud\n"
        "- Match eenheden op basis van naamovereenkomst met de afdeling,"
        " of op basis van de opdracht-inhoud\n"
        "- Geef per match een confidence score (0.0-1.0)\n"
        "- Geef een korte reden in het Nederlands\n"
        "- Stel een rol voor: 'contactpersoon', 'betrokken', of 'eigenaar'\n"
        "- Geef ALLEEN matches met confidence >= 0.5\n"
        "- Als er geen goede matches zijn, geef een lege lijst\n\n"
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "matches": [\n'
        "    {\n"
        '      "target_id": "uuid van de persoon of eenheid",\n'
        '      "link_type": "person" of "organisatie_eenheid",\n'
        '      "confidence": 0.85,\n'
        '      "reason": "Naam komt overeen met contactpersoon opdrachtgever",\n'
        '      "suggested_rol": "contactpersoon",\n'
        '      "source_field": "Contactpersoon_opdrachtgever" of null\n'
        "    }\n"
        "  ]\n"
        "}"
    )


CHAT_SYSTEM_PROMPT = (
    "Je bent de Bouwmeester-assistent, een AI-hulpmiddel voor beleidsmedewerkers"
    " van het ministerie van BZK (Binnenlandse Zaken en Koninkrijksrelaties)."
    " Je helpt gebruikers met het beheren van het beleidscorpus: nodes zoeken,"
    " relaties leggen, taken aanmaken, organisatie verkennen, opdrachten"
    " bekijken, en het beleidsgrafiek navigeren.\n\n"
    "BESCHIKBARE NODE-TYPES:\n"
    "- dossier: beleidsdossier\n"
    "- doel: beleidsdoel\n"
    "- instrument: beleidsinstrument\n"
    "- beleidskader: beleidskader\n"
    "- maatregel: beleidsmaatregel\n"
    "- politieke_input: politieke input\n"
    "- probleem: beleidsprobleem\n"
    "- effect: beleidseffect\n"
    "- beleidsoptie: beleidsoptie\n"
    "- bron: bron\n\n"
    "BESCHIKBARE RELATIE-TYPES:\n"
    "implementeert, draagt_bij_aan, vloeit_voort_uit, conflicteert_met,"
    " verwijst_naar, vereist, evalueert, vervangt, onderdeel_van,"
    " leidt_tot, adresseert, meet, gerelateerd_aan\n\n"
    "TAAK-STATUSSEN: open, in_progress, done, cancelled\n"
    "TAAK-PRIORITEITEN: laag, normaal, hoog, kritiek\n"
    "SUBTAKEN: gebruik parent_task_id in create_task om een subtaak"
    " te maken onder een bestaande taak. Zoek eerst de bovenliggende"
    " taak op met get_tasks_for_node.\n\n"
    "STAKEHOLDER-ROLLEN: eigenaar, betrokken, adviseur\n\n"
    "OPDRACHT-STATUSSEN: concept, actief, afgerond, verantwoord, geannuleerd\n"
    "OPDRACHT-TYPES: opdracht, subsidie\n\n"
    "ORGANISATIE-TYPES: Ministerie, Directoraat-Generaal, Directie, Afdeling, Team\n\n"
    "KLIKBARE LINKS:\n"
    "Wanneer je verwijst naar een entiteit, maak er een klikbare link"
    " van zodat de gebruiker er direct naartoe kan navigeren. Gebruik"
    " deze markdown link-formaten:\n"
    "- Nodes: [Titel van node](bm://node/<UUID>)\n"
    "- Taken: [Titel van taak](bm://task/<UUID>)\n"
    "Gebruik altijd de naam/titel als linktekst, niet het UUID.\n\n"
    "LEAD FUNNEL (SALES PIPELINE):\n"
    "Je kunt ook leads beheren in de sales funnel. Leads zijn organisaties\n"
    "of personen die interesse hebben in het product/dienst.\n\n"
    "LEAD-STAGES (in volgorde van de pipeline):\n"
    "- verkennen: eerste verkenning\n"
    "- eerste_gesprek: eerste gesprek ingepland/gevoerd\n"
    "- interne_check: interne check of het past\n"
    "- follow_up: follow-up na gesprek\n"
    "- in_the_pocket: deal gesloten\n"
    "- koelkast: on hold / niet nu\n\n"
    "LEAD-ACTIVITEIT-TYPES: note, meeting, call, email\n\n"
    "KLIKBARE LINKS VOOR LEADS:\n"
    "- Leads: [Titel van lead](bm://lead/<UUID>)\n\n"
    "REGELS:\n"
    "- Antwoord altijd in het Nederlands.\n"
    "- Gebruik de beschikbare tools om informatie op te zoeken en acties"
    " uit te voeren. Beantwoord vragen niet uit je hoofd als je het kunt"
    " opzoeken.\n"
    "- Bij schrijfacties (aanmaken, wijzigen): het systeem toont automatisch"
    " een bevestigingsknop. Vraag de gebruiker NIET zelf om bevestiging"
    " in je tekst — geen 'wil je bevestigen?', 'zal ik doorgaan?', etc.\n"
    "- Verwijs naar entiteiten bij naam en maak ze klikbaar met het"
    " bm://-linkformaat.\n"
    "- Wees beknopt en to-the-point.\n"
    "- Als je meerdere resultaten vindt, geef een overzicht met de"
    " belangrijkste informatie.\n"
    "- Als je taken voor een node zoekt, gebruik get_tasks_for_node.\n"
    "- Als je taken voor een persoon zoekt, gebruik get_tasks_for_person.\n"
    "- Als je verlopen taken wilt, gebruik get_overdue_tasks.\n"
    "- Als je opdrachten/subsidies zoekt, gebruik list_opdrachten.\n"
    "- Als je organisatie-eenheden zoekt, gebruik search_organisatie.\n"
    "- Als je vergelijkbare nodes zoekt, gebruik find_similar_nodes.\n"
    "- Als je het pad tussen twee nodes wilt, gebruik find_path.\n\n"
    "BESTANDEN EN AFBEELDINGEN:\n"
    "De gebruiker kan bestanden uploaden bij hun bericht (afbeeldingen, PDF's,\n"
    "Word-documenten). Analyseer de inhoud en gebruik deze als context.\n"
    "- Bij afbeeldingen: beschrijf wat je ziet en beantwoord vragen erover\n"
    "- Bij documenten: de tekst is geëxtraheerd en meegegeven als context\n"
    "- Je kunt bronnen (type=bron) aanmaken op basis van geüploade documenten\n"
    "- Je kunt een geüpload bestand koppelen aan een bestaande bron-node met\n"
    "  attach_to_bron (geef attachment_id en node_id op). Het bestand wordt\n"
    "  dan als officiële bijlage aan de bron gekoppeld.\n"
    "- Verwijs naar geüploade bestanden bij naam in je antwoord\n\n"
    "PRESENTATIE — HEEL BELANGRIJK:\n"
    "- Toon NOOIT UUIDs, interne IDs, of technische details aan de"
    " gebruiker. Gebruik altijd namen en titels.\n"
    "- Toon NOOIT ruwe tool-aanroepen, JSON, of systeemberichten.\n"
    "- Herhaal NIET de contextinformatie (zoals welke pagina of node"
    " de gebruiker bekijkt) terug aan de gebruiker.\n"
    "- Vermeld GEEN interne opmerkingen over bevestigingsprocessen"
    " of taak-IDs die nog niet definitief zijn.\n"
    "- Schrijf als een behulpzame collega, niet als een systeem.\n"
    "- FORMATTING: Gebruik geldige Markdown. Gebruik ### voor kopjes,"
    " NIET nummers op een eigen regel gevolgd door vetgedrukte tekst."
    " Gebruik genummerde lijsten (1. item) alleen als echte lijsten,"
    " niet als kopjes. Houd antwoorden compact.\n"
)


def build_chat_context_message(context: dict | None) -> str:
    """Build a context-awareness message from the current UI state."""
    if not context:
        return ""
    parts = []
    page = context.get("page", "")
    if page:
        page_labels = {
            "/": "Inbox",
            "/corpus": "Corpus (node-overzicht)",
            "/tasks": "Taken",
            "/people": "Personen",
            "/organisatie": "Organisatie",
            "/search": "Zoeken",
            "/parlementair": "Parlementair",
            "/opdrachten": "Opdrachten",
            "/leads": "Leads (sales funnel)",
            "/admin": "Beheer",
        }
        label = page_labels.get(page, page)
        parts.append(f"De gebruiker bekijkt momenteel de pagina: {label}")
    node_id = context.get("node_id")
    node_title = context.get("node_title")
    node_type = context.get("node_type")
    if node_title and node_id:
        type_label = _NODE_TYPE_LABELS.get(node_type or "", node_type or "node")
        parts.append(
            f"Specifiek bekijkt de gebruiker {type_label}:"
            f' "{node_title}" (ID: {node_id})'
        )
    elif node_id:
        parts.append(f"De gebruiker bekijkt een node (ID: {node_id})")
    node_description = context.get("node_description")
    if node_description:
        parts.append(f"Beschrijving van de node: {node_description[:300]}")
    task_id = context.get("task_id")
    task_title = context.get("task_title")
    if task_title and task_id:
        parts.append(f'Er is een taak geselecteerd: "{task_title}" (ID: {task_id})')
    elif task_id:
        parts.append(f"Er is een taak geselecteerd (ID: {task_id})")

    lead_id = context.get("lead_id")
    lead_title = context.get("lead_title")
    if lead_title and lead_id:
        parts.append(f'De gebruiker bekijkt lead: "{lead_title}" (ID: {lead_id})')
    elif lead_id:
        parts.append(f"De gebruiker bekijkt een lead (ID: {lead_id})")

    # Include inline @ and # mentions from the user's message
    mentions = context.get("mentions", [])
    if mentions:
        mention_parts = []
        for m in mentions:
            mention_parts.append(f"- {m['label']} (type: {m['type']}, ID: {m['id']})")
        parts.append(
            "De gebruiker verwijst naar de volgende entiteiten:\n"
            + "\n".join(mention_parts)
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Mattermost-meelees-prompts
# ---------------------------------------------------------------------------


MAX_RECENT_LEADS_IN_PROMPT = 60


def build_classify_mattermost_lead_prompt(
    *,
    message: str,
    initiatief_naam: str,
    channel_display_name: str,
    recent_leads: list[dict],
) -> str:
    """Bouw een prompt voor het classificeren van een Mattermost-bericht
    als (potentiële) lead binnen een initiatief.

    ``recent_leads`` is een lijst dicts ``{id, title, organization, stage}``
    van leads binnen hetzelfde initiatief, zodat de LLM duplicaten kan
    voorstellen. De caller bepaalt de selectie (recency + trigram-
    similarity); deze functie cap't alleen op ``MAX_RECENT_LEADS_IN_PROMPT``.
    """
    leads_block = ""
    if recent_leads:
        items = []
        for lead in recent_leads[:MAX_RECENT_LEADS_IN_PROMPT]:
            org = lead.get("organization")
            org_part = f', organisatie: "{org}"' if org else ""
            items.append(
                f"- id: {lead['id']}, "
                f'titel: "{lead["title"]}"'
                f"{org_part}, "
                f"stage: {lead.get('stage', '?')}"
            )
        leads_block = (
            "\nBESTAANDE LEADS in dit initiatief (kandidaten voor 'koppelen'):\n"
            + "\n".join(items)
            + "\n"
        )

    return (
        "Je bent een medewerker van team Regelrecht bij het ministerie van BZK.\n"
        f'Het Mattermost-kanaal "{channel_display_name}" is gekoppeld aan'
        f' het initiatief "{initiatief_naam}". In dit kanaal worden nieuwe'
        " leads (organisaties of mensen die geïnteresseerd zijn in onze"
        " dienstverlening) besproken.\n\n"
        "Beoordeel of het volgende bericht een nieuwe of bestaande lead"
        " beschrijft. Een lead is een concreet contactmoment of signaal"
        " van een externe organisatie/persoon — niet een collega die"
        " intern iets meldt of een algemene update.\n\n"
        f"BERICHT:\n{message[:MAX_TEXT_IN_PROMPT]}\n"
        f"{leads_block}\n"
        "Antwoord met JSON (en ALLEEN JSON):\n"
        "{\n"
        '  "is_lead": true|false,\n'
        '  "confidence": 0.0-1.0,\n'
        '  "proposed_title": "korte titel (organisatie of '
        'onderwerp), max 80 chars",\n'
        '  "proposed_description": "1-2 zinnen samenvatting wat ze willen",\n'
        '  "match_existing_lead_id": "uuid van bestaande lead of null",\n'
        '  "reasoning": "kort waarom je dit denkt (max 1 zin)"\n'
        "}\n"
        "Regels:\n"
        '- Bij twijfel: "is_lead": false. Beter een gemiste suggestie'
        " dan ruis.\n"
        '- Triviale berichten ("ok", "👍", "morgen even bellen")'
        ' krijgen "is_lead": false.\n'
        "- Als het overduidelijk over een bestaande lead uit de lijst"
        ' gaat, vul "match_existing_lead_id" met die UUID en houd'
        ' "is_lead": true.\n'
        '- Als geen match: "match_existing_lead_id": null.'
    )


def build_is_noise_prompt(message: str) -> str:
    """Bouw een prompt die ruis-berichten als zodanig markeert.

    Ruis = ack-berichten, korte emoji-replies, "ok", "👍", lege thread-pings.
    Géén ruis = inhoudelijke updates, vragen, beschrijvingen — ook al zijn
    ze kort.
    """
    return (
        "Beoordeel of dit Mattermost-bericht ruis is (ack, emoji-only,"
        " social chit-chat zonder inhoudelijke informatie) of een"
        " inhoudelijke notitie die op een lead bewaard zou moeten worden."
        " Bij twijfel: niet-ruis.\n\n"
        f"BERICHT:\n{message[:2000]}\n\n"
        "Antwoord met JSON (en ALLEEN JSON):\n"
        '{"is_noise": true|false}'
    )


def build_summarize_mattermost_thread_prompt(
    *, message: str, max_words: int = 80
) -> str:
    """Bouw een prompt voor het samenvatten van een (lang) MM-bericht."""
    return (
        "Vat onderstaand Mattermost-bericht samen in maximaal"
        f" {max_words} woorden, in het Nederlands. Behoud concrete feiten,"
        " namen, datums en deadlines. Geen meta-commentaar, geen"
        " inleiding."
        f"\n\nBERICHT:\n{message[:MAX_TEXT_IN_PROMPT]}\n\n"
        "Antwoord met JSON (en ALLEEN JSON):\n"
        '{"samenvatting": "..."}'
    )
