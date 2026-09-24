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

    vensters = _begrensd(_samengevoegd(vindplaatsen, len(tekst)))

    # Op waarde kiezen, maar op volgorde tonen. Zonder de weging pakte dit
    # simpelweg de eerste vensters tot het budget op was, en bij een
    # verslag van een schriftelijk overleg is dat systematisch de
    # verkeerde helft: de inleiding en de procedurele kop staan vooraan,
    # de vragen staan achterin.
    #
    # Gemeten geval, 2026D45836 (43.185 tekens, 69 vraagtekens): de
    # passage waarin een fractie vraagt welke rol de Digitale Dienst
    # krijgt bij het cloudbeleid staat op teken 22.983, en viel buiten de
    # selectie. Dat was juist de alinea die een lezer eruit haalde.
    gekozen = sorted(
        sorted(vensters, key=lambda v: _waarde(tekst, v, termen), reverse=True)[
            : _past_er_in(budget, overhead)
        ]
    )

    for start, eind in gekozen:
        if budget <= overhead:
            break
        # De kop gaat er los bij, dus een venster dat daarin valt levert
        # dezelfde tekst twee keer op. Dat kostte bij 2026D45836 1.100
        # tekens aan een herhaalde voorpagina, ten koste van een passage
        # met vragen.
        if eind <= len(kop):
            continue
        start = max(start, len(kop))
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


# Een samengevoegd venster mag niet zo groot worden dat er maar één of
# twee in het budget passen. Gemeten geval, 2026D45836: 71 vindplaatsen
# smolten samen tot 12 vensters van 1.200 tot 9.027 tekens, waarvan er
# twee in het budget pasten. De derde was juist de passage met de vragen.
MAX_VENSTER = 2200


def _begrensd(vensters: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Hak te grote vensters in stukken, in plaats van ze af te kappen.

    Samenvoegen voorkomt dubbele tekst, maar bij een stuk waarin de term
    overal valt groeit één blok door tot het de halve selectie opeet. Bij
    2026D45836 werd dat een venster van 19.837 tot 23.739, en de passage
    met de vragen stond op 22.983.

    Afkappen op de start zou die passage net zo goed weggooien; in
    stukken hakken laat elk deel apart meewegen, zodat de helft met de
    vragen kan winnen van de helft met de inleiding.
    """
    uit: list[tuple[int, int]] = []
    for start, eind in vensters:
        positie = start
        while positie < eind:
            uit.append((positie, min(eind, positie + MAX_VENSTER)))
            positie += MAX_VENSTER
    return uit


def _past_er_in(budget: int, overhead: int) -> int:
    """Hoeveel vensters er hooguit in het budget passen.

    Ruim geschat op het kleinst denkbare venster, zodat de weging kiest
    welke vensters meegaan en de lus daarna afkapt op de echte lengtes.
    """
    per_venster = overhead + 1
    return max(1, budget // per_venster)


# Een vraagteken maakt een passage waardevoller dan een kop met dezelfde
# term erin: bij een kamerstuk is wat er gevraagd wordt doorgaans het
# nieuws, en een inhoudsopgave die de term vijf keer noemt is dat niet.
_VRAAG = re.compile(r"\w[^.?!]{9,}\?")

# Woorden die een passage markeren waarin iets gebeurt of gevraagd wordt.
# Bewust kort gehouden: dit is een duw in de goede richting, geen poging
# om te begrijpen wat er staat.
_SIGNAALWOORDEN = (
    "vraag",
    "vragen",
    "verzoek",
    "verzoeken",
    "toezegging",
    "motie",
    "wanneer",
    "waarom",
    "welke",
    "hoe ",
    "kan het kabinet",
    "is de staatssecretaris",
    "is de minister",
)


def _waarde(tekst: str, venster: tuple[int, int], termen: list[str]) -> float:
    """Hoe bruikbaar is deze passage voor een alert?

    Drie dingen tellen mee, in aflopende zwaarte: hoe vaak de zoekterm
    er valt, of er een vraag in staat, en of er signaalwoorden staan.
    Zonder dit is de volgorde in het document de enige maatstaf, en die
    zegt niets over waar het onderwerp behandeld wordt.
    """
    start, eind = venster
    fragment = tekst[start:eind]
    klein = fragment.lower()

    treffers = 0
    for term in termen:
        kern = term.strip().strip('"').lower()
        if len(kern) >= 3:
            treffers += klein.count(kern)

    # Alleen vraagtekens die aan een zin hangen. Een losse reeks "? ? ?"
    # (opmaakresten uit een docx, of een tabel) is geen vraag, en zonder
    # deze eis scoorde zulke rommel hoger dan een echte kamervraag.
    vragen = len(_VRAAG.findall(fragment))
    signalen = sum(1 for woord in _SIGNAALWOORDEN if woord in klein)

    # Een vraag zonder enige zoekterm in de buurt telt niet mee: dit gaat
    # om passages over ónze zoekterm, niet om de vraagdichtheid van het
    # stuk.
    if treffers == 0:
        vragen = 0
        signalen = 0

    # De term weegt het zwaarst (daar kwam het stuk op binnen), een vraag
    # daarna, signaalwoorden als kleine correctie. De aantallen worden
    # begrensd zodat één alinea met twintig vraagtekens niet de hele
    # selectie opeet.
    return min(treffers, 5) * 3.0 + min(vragen, 4) * 2.0 + min(signalen, 4) * 0.5


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
