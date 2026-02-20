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
