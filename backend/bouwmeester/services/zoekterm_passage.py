"""Knip de passages waar de zoekterm valt uit een lang document.

Het probleem dat dit oplost, gemeten op 22 september 2026: de memorie van
toelichting bij de EZ-begroting (2026D38772) is 409.830 tekens. De
extractie kapt op 15.000, dus 394.830 tekens gingen ongezien. Alle twee de
vindplaatsen van "Nederlandse Digitale Dienst" vielen daarbuiten — op
positie 44.954 en 262.182 — en juist daar staat wat de dienst gaat doen:

    "Ten slotte wordt in 2027 verder gewerkt aan de ontwikkeling van de
    Nederlandse Digitale Dienst (NDD), gericht op het leveren van
    meerwaarde voor burgers en ondernemers langs drie sporen: (1) een
    doorbraakfunctie voor prioritaire projecten, (2) het vaststellen van
    standaarden..."

Het model zag alleen de voorpagina met begrotingsstaten en gaf een
relevantiescore van 8. Dat was geen oordeel maar een artefact van het
venster: een begroting of een verzamelwet noemt jouw onderwerp nu eenmaal
ergens in het midden.

Dus: zoek de vindplaatsen en stuur die mee, met genoeg tekst eromheen om
ze te kunnen duiden. De kop van het document gaat er los bij, want die
vertelt waar het stuk over gaat.
"""

import re

# Hoeveel tekens rond elke vindplaats. Ruim genoeg voor de alinea eromheen,
# klein genoeg om er meerdere te kunnen meesturen.
CONTEXT_TEKENS = 1200

# De kop zegt waar het document over gaat; zonder die context leest een
# passage uit het midden van een begroting als een losse zin.
KOP_TEKENS = 800

# Bovengrens op wat we samenstellen. Blijft onder de MAX_TEXT_IN_PROMPT van
# 10.000 die de prompt zelf hanteert, zodat de prompt niets meer afkapt.
MAX_TOTAAL = 9000

# Voorbij deze lengte knippen we; korte stukken gaan in hun geheel mee,
# want dan is de hele tekst de context.
KNIP_VANAF = 6000


def knip_rond_termen(tekst: str, termen: list[str]) -> str:
    """Geef de kop plus de passages waar een van de termen valt.

    Valt geen enkele term in de tekst (bijvoorbeeld omdat de extractie hem
    al had afgekapt, of omdat tkconv op een bijlage matchte die wij niet
    zien), dan komt het begin terug. Dat is niet ideaal, maar beter dan een
    lege prompt.
    """
    if not tekst:
        return ""
    if len(tekst) <= KNIP_VANAF:
        return tekst

    vindplaatsen = _vindplaatsen(tekst, termen)
    if not vindplaatsen:
        return tekst[:MAX_TOTAAL]

    kop = tekst[:KOP_TEKENS].strip()
    delen = [kop] if kop else []
    # Elk volgend deel kost naast het fragment zelf ook de scheiding
    # ("\n\n") en de weglatingsmarkering ("[...]\n"). Die tellen mee in het
    # budget, anders komt het resultaat net boven de grens uit en kapt de
    # prompt alsnog af — precies het probleem dat dit bestand oplost.
    overhead = len("\n\n") + len("[...]\n")
    budget = MAX_TOTAAL - len(kop)

    for start, eind in _samengevoegd(vindplaatsen, len(tekst)):
        if budget <= overhead:
            break
        fragment = tekst[start:eind].strip()
        ruimte = budget - overhead
        if len(fragment) > ruimte:
            fragment = fragment[:ruimte]
        if not fragment:
            break
        # Zeg erbij dat er iets tussen zit weggelaten, anders leest het
        # model twee losse passages als één doorlopend betoog.
        delen.append(f"[...]\n{fragment}")
        budget -= len(fragment) + overhead

    return "\n\n".join(delen)


def _vindplaatsen(tekst: str, termen: list[str]) -> list[int]:
    """Waar valt een van de termen? Gesorteerd, zonder duplicaten."""
    posities: set[int] = set()
    for term in termen:
        kern = term.strip().strip('"')
        if len(kern) < 3:
            continue
        for match in re.finditer(re.escape(kern), tekst, re.IGNORECASE):
            posities.add(match.start())
    return sorted(posities)


def _samengevoegd(posities: list[int], lengte: int) -> list[tuple[int, int]]:
    """Vensters rond de vindplaatsen, overlappende samengevoegd.

    Twee vermeldingen vlak bij elkaar leveren anders twee vensters op die
    grotendeels dezelfde tekst bevatten, en dat gaat ten koste van een
    derde vindplaats verderop.
    """
    vensters: list[tuple[int, int]] = []
    for positie in posities:
        start = max(0, positie - CONTEXT_TEKENS // 2)
        eind = min(lengte, positie + CONTEXT_TEKENS // 2)
        if vensters and start <= vensters[-1][1]:
            vensters[-1] = (vensters[-1][0], max(vensters[-1][1], eind))
        else:
            vensters.append((start, eind))
    return vensters
