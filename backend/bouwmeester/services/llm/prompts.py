"""Shared prompt templates for BZK policy domain (Dutch)."""

import json

# Maximum number of tags to include in prompts to control token usage.
MAX_TAGS_IN_PROMPT = 200
MAX_TEXT_IN_PROMPT = 10000

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
        source += f"\nBESCHRIJVING: {source_description[:500]}"

    target = f"TITEL: {target_title}"
    if target_description:
        target += f"\nBESCHRIJVING: {target_description[:500]}"

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
        " gerelateerd_aan, draagt_bij_aan, onderdeel_van,"
        " beïnvloedt, implementeert\n"
        "- Geef een korte reden in het Nederlands\n\n"
        "Geef je analyse als JSON"
        " (en ALLEEN JSON, geen andere tekst):\n"
        "{\n"
        '  "score": 0.8,\n'
        '  "suggested_edge_type": "gerelateerd_aan",\n'
        '  "reason": "Beide nodes gaan over ..."\n'
        "}"
    )


def build_summarize_prompt(text: str, max_words: int = 100) -> str:
    return (
        "Je bent een beleidsanalist van het ministerie van BZK."
        " Vat de volgende tekst beknopt samen in het Nederlands."
        f" Gebruik maximaal {max_words} woorden.\n\n"
        f"TEKST:\n{text[:MAX_TEXT_IN_PROMPT]}\n\n"
        "SAMENVATTING:"
    )
