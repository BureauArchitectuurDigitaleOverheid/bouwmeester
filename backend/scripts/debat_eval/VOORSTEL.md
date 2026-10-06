# Voorstel: betere vraagmarkering en vier nieuwe soorten

Dit voorstel volgt uit de eerste meting met de harness in deze map (zie
`README.md`). De gouden set staat niet in de repository. Alle getallen hieronder
komen uit die set; er staan geen citaten uit echte debatten in dit stuk. De
voorbeelden zijn verzonnen en komen uit de fixture.

## Waarop gemeten is

Vier debatten van 5 en 6 oktober 2026: een notaoverleg over een initiatiefnota
(met initiatiefnemers en een minister), een wetgevingsoverleg (met een minister),
het eerste kwartier van een tweede notaoverleg, en ruim een uur uit de eerste
termijn van een plenaire begrotingsbehandeling. Samen 328 beurten en 5,8 uur
spraak. De opnames hebben gaten: van het eerste debat ontbreekt de tweede
termijn, van het tweede een deel van het antwoord van de minister.

| Soort | Zeker | Onzeker | Herhaling | Per uur spraak (zeker) |
|---|---|---|---|---|
| vraag | 134 | 16 | 1 | 23,1 |
| toezegging | 12 | 6 | 8 | 2,1 |
| verzoek_om_brief | 6 | 4 | 0 | 1,0 |
| motie | 11 | 2 | 1 | 1,9 |
| feitelijke_claim | 54 | 11 | 0 | 9,3 |

Daarnaast 191 lastige negatieven. Eén persoon heeft gelabeld, zonder tweede
lezer.

Model: `claude-haiku-4-5-20251001` via de Claude-CLI, de standaardwaarde van
`LLM_MODEL`. Of productie hetzelfde model gebruikt heb ik niet kunnen nagaan.

## De vraag: waar het nu staat

De huidige prompt is twee keer over de hele set gedraaid. Van de 328 beurten
slaat de code er 193 over; het model zag er 135.

| Run | Gemarkeerd | Goed | Fout | Precisie | Recall |
|---|---|---|---|---|---|
| Huidige prompt, run 1 | 191 | 135 | 53 | 72% | 96% |
| Huidige prompt, run 2 | 182 | 128 | 51 | 72% | 95% |

De recall is goed: van de 134 zekere vragen mist het model er 5 of 6, en één
valt weg omdat hij door de tijdtoewijzing in de beurt van de minister staat.
Het probleem zit in de precisie. Ruim een kwart van wat in het kanaal komt is
geen vraag aan de bewindspersoon.

Waar de 53 en 51 foute markeringen uit bestaan:

| Wat | Run 1 | Run 2 |
|---|---|---|
| Een bewering waar een vraag van is gemaakt | 32 | 21 |
| Over het kabinet, niet aan het kabinet (uitspraak over het kabinet, oproep, naverteld vraag, aangehaalde toezegging) | 7 | 8 |
| De tekst van een motie die wordt voorgelezen | 6 | 9 |
| Retorisch, zonder adressaat, aan een Kamerlid of aan de initiatiefnemers | 8 | 13 |

De eerste rij is het probleem dat in productie is gezien. Het model neemt een
zin over als "Niemand kan mij vertellen waar de 30 miljoen aan is uitgegeven"
en schrijft er in de samenvatting een nette vraag bij. Het citaat klopt
letterlijk, dus de controle op het citaat houdt dit niet tegen. In 28 van de 32
gevallen stond de zin niet eens in mijn lijst van lastige negatieven: het zijn
gewone betogen, vaak van een Kamerlid dat een collega antwoordt of van een
initiatiefnemer die vragen beantwoordt.

Twee dingen die buiten de twee bekende problemen vallen:

- In de beurten van de initiatiefnemers stond geen enkele zekere vraag aan de
  minister, en het model markeerde er 9 dingen (run 1). De code weet nu alleen
  dat er initiatiefnemers zijn, niet wie het zijn.
- Het verschil tussen twee runs met dezelfde prompt is groot: 32 tegen 21
  beweringen. Eén run zegt weinig over een verandering van een paar punten.

## De vraag: wat ik zou veranderen

### 1. Twee alinea's in de prompt

De tekst staat in `variants.py` (`IN_THE_QUOTE` en `ABOUT_IS_NOT_TO`) en komt
vóór de kop "Wat verder niet telt". De eerste zegt dat in het citaat de woorden
moeten staan waarmee de spreker vraagt, en dat van een bewering geen vraag
gemaakt wordt. De tweede zegt dat een zin waarin het kabinet voorkomt nog geen
vraag aan het kabinet is, met vier gevallen: een uitspraak over het kabinet,
iets wat tegen een ander Kamerlid over het kabinet wordt gezegd, een oproep
zonder vraag, en een vraag van eerder die wordt naverteld.

Gemeten door de productieprompt onderweg naar het model te herschrijven, twee
runs:

| Run | Gemarkeerd | Goed | Fout | Precisie | Recall | Beweringen |
|---|---|---|---|---|---|---|
| Met beide alinea's, run 1 | 171 | 129 | 39 | 77% | 93% | 19 |
| Met beide alinea's, run 2 | 178 | 133 | 42 | 76% | 96% | 22 |

Dat is ongeveer twaalf foute markeringen minder per run en vier à vijf punten
precisie, zonder aantoonbaar verlies aan recall. Het aantal beweringen ligt
onder dat van de eerste run met de huidige prompt en gelijk aan dat van de
tweede; met twee runs per variant kan ik niet zeggen dat de prompt dit ene
probleem oplost. Het model markeert ook met de nieuwe tekst nog het voorbeeld
dat er bijna letterlijk in staat. De prompt alleen is dus niet genoeg.

### 2. Een controle in de code: het citaat heeft de vorm van een vraag

In `lees_antwoord`, naast de controle dat het citaat in de beurt staat: het
citaat moet zelf een vraag of een verzoek bevatten. `has_question_form` in
`variants.py` is een eerste versie. Het zegt ja bij een vraagteken, bij de
woorden van een verzoek ("mijn vraag", "graag een reactie", "kan hij
toezeggen", "ik ben benieuwd"), bij een zinsdeel dat met een vraagwoord begint,
en bij een zinsdeel dat begint met een persoonsvorm gevolgd door wie gevraagd
wordt ("kan de minister", "deelt het kabinet", "trekken we"). Bij twijfel zegt
het ja.

Op de gouden set: 149 van de 151 vragen hebben die vorm (de twee zonder zijn
allebei als onzeker gelabeld). Van de negatieven houdt het 31 van de 32
uitspraken over het kabinet tegen en 10 van de 11 oproepen. Retorische vragen
en vragen aan anderen laat het door; die hebben de vorm van een vraag.

### 3. Een controle in de code: de tekst van een motie is geen vraag

"Verzoekt de regering", "gaat over tot de orde van de dag", "gehoord de
beraadslaging", "overwegende dat", "constaterende dat". Wie een motie voorleest
vraagt in vorm iets aan de regering, en het model markeert het dictum als
vraag: 6 tot 9 keer per run. Dit is `is_motion_text` in `variants.py`.

### Wat de controles opleveren

Toegepast op de opgeslagen runs, zonder het model opnieuw te vragen:

| Run | Controles | Gemarkeerd | Goed | Fout | Precisie | Recall |
|---|---|---|---|---|---|---|
| Huidige prompt, run 1 | geen | 191 | 135 | 53 | 72% | 96% |
| Huidige prompt, run 1 | beide | 158 | 130 | 27 | 83% | 95% |
| Huidige prompt, run 2 | beide | 148 | 123 | 24 | 84% | 93% |
| Nieuwe prompt, run 1 | beide | 148 | 125 | 20 | 86% | 91% |
| Nieuwe prompt, run 2 | beide | 150 | 129 | 20 | 87% | 94% |

De controles doen meer dan de prompt: de helft van de foute markeringen
verdwijnt. De prijs is één tot drie zekere vragen per run en vier of vijf goede
markeringen. Dat zijn gevallen waarin het model de aanloop van een vraag
citeert en de vraagzin zelf net niet meeneemt. Dat is te repareren door de
controle ook de zin na het citaat te laten lezen; dat heb ik niet gemeten.

Twee kanttekeningen. De vraagvorm-controle is op deze set afgesteld, dus op
nieuwe debatten zal hij iets slechter zijn. En 28 beweringen zijn pas als
negatief gelabeld nadat het model ze had gemarkeerd.

### 4. Weten wie de initiatiefnemers zijn

Geef `DebatContext` de namen van de initiatiefnemers en sla hun beurten over,
of laat alleen een vraag met "de minister" erin door. In deze set kost dat geen
enkele zekere vraag (wel drie onzekere, van het type "ik ben benieuwd hoe de
minister daartegen aankijkt") en scheelt het 9 foute markeringen in één debat. Eén
debat is weinig; meet het opnieuw bij het volgende debat met initiatiefnemers.

### Wat ik niet zou doen

De beurt overslaan waarin een Kamerlid een interruptie van een collega
beantwoordt. Daar zitten 17 foute markeringen in run 1, maar de code kan zo'n
beurt niet onderscheiden van het vervolg van iemands termijn na een
interruptie, en in die beurten staan 15 zekere vragen.

## De vier nieuwe soorten

### motie: als eerste

**Definitie.** Een Kamerlid kondigt een motie aan of leest er een voor.

**Wie.** Een Kamerlid, in de eigen termijn of in een interruptie. Niet de
voorzitter, niet de bewindspersoon (die geeft een oordeel).

**Wat er in het citaat moet staan.** Bij een voorgelezen motie het dictum: van
"verzoekt de regering" tot en met "gaat over tot de orde van de dag". Bij een
aankondiging het woord "motie" met een werkwoord van indienen in de eerste
persoon ("ik zal een motie indienen", "ik dien de volgende motie in").

**In de set.** 11 zeker, waarvan 9 voorgelezen en 2 aangekondigd; 2 onzeker
("ik overweeg een motie"); 1 herhaling. 1,9 per uur, bijna allemaal in de
tweede termijn, en van één debat ontbreekt die. De opening van een motie staat
in één geval in de beurt van de voorzitter, door de tijdtoewijzing.

**Typische fouten.** "Dan scheelt mij dat een motie" (1 keer). Een motie die
eerder is aangenomen en nu wordt genoemd ("de motie die vorig jaar is
aangenomen"): ik heb ze niet geteld als negatief, het zijn er ten minste 8.
De controle moet dus eisen dat de spreker zelf nu indient of aankondigt.

**Waarom eerst.** De voorgelezen motie is aan vaste formules te herkennen, dus
een groot deel kan zonder model of met een eenvoudige controle achteraf. En de
soort haalt 6 tot 9 foute vragen per run weg. Per motie is ook duidelijk wat
het ministerie ermee moet: een oordeel voorbereiden.

### toezegging: als tweede, en het meeste werk

**Definitie.** De bewindspersoon verbindt zich aan iets waar de Kamer hem aan
kan houden: een brief, een datum, er schriftelijk of in een genoemde
rapportage op terugkomen, iets uitzoeken, iets opnemen met een ander.

**Wie.** Alleen een bewindspersoon. Dat zijn precies de beurten die de code nu
overslaat, dus dit vraagt een tweede prompt voor een ander soort beurt. In de
twee debatten met een antwoord van de minister gaat het om 38 beurten.

**Wat er in het citaat moet staan.** Een werkwoord van toezeggen of doen in de
eerste persoon ("ik zeg toe", "ik zal", "ik kom erop terug", "ik neem dat
mee", "de Kamer krijgt") en iets wat geleverd wordt of een moment. Zonder een
van die twee is het een voornemen.

**In de set.** 12 zeker, 6 onzeker, 8 herhalingen. In de twee debatten met een
antwoord 2,7 per uur. Van de 26 staan er 21 in een beurt van de
bewindspersoon, 2 in de beurt van het Kamerlid dat interrumpeerde (door de
tijdtoewijzing; de stemherkenning in productie zal een deel hiervan
rechtzetten) en 3 in de slotbeurt van de voorzitter.

**Typische fouten.** Lopend beleid ("wij zijn op dit moment in gesprek over",
3). Er later in hetzelfde antwoord op terugkomen (2). Wat een collega-minister
heeft toegezegd (1). Een Kamerlid dat een toezegging aanhaalt (3). En de
zes onzekere: een inspanning zonder iets wat geleverd wordt ("ik ga kijken of
dat lukt"), een voorwaarde bij het oordeel over een motie.

**De lijst van de voorzitter.** Aan het eind van een commissiedebat leest de
voorzitter de toezeggingen voor. In het ene debat waarvan het eind is
opgenomen waren dat er drie. Twee daarvan had ik in het antwoord van de
minister gevonden, de derde viel in een gat in de opname, en één toezegging
die ik als zeker had gelabeld (een Kamerbrief die al in voorbereiding was)
stond niet op de lijst. Die lijst is strenger dan mijn codeboek en is wat de
griffie registreert. Lees de slotbeurt van de voorzitter uit als bevestiging:
een toezegging die op de lijst staat is zeker, een die er niet op staat blijft
een kandidaat. Plenair is er geen lijst.

**Herhaling.** Een toezegging wordt herhaald, aangescherpt en bevestigd: 8 van
de 26. Het model van vraag en vermelding past hier ook, maar dan per
bewindspersoon in plaats van per vragensteller.

**Waarom tweede.** Dit is waar ambtenaren het meest aan hebben en er is een
bron om tegen te controleren. Het kost het meeste: een nieuwe prompt, een
verdubbeling van het aantal beurten dat naar het model gaat, en de koppeling
van een toezegging aan de vraag die hij beantwoordt.

### verzoek_om_brief: nog niet als eigen soort

**Definitie.** Een Kamerlid vraagt de bewindspersoon om iets op papier: een
brief, een overzicht, een rapportage, of "de Kamer informeren" met een moment
of een vorm erbij.

**In de set.** 6 zeker, 4 onzeker. Eén per uur.

**Waarom niet.** Het is een vraag aan de bewindspersoon met een kenmerk erbij.
De huidige prompt vangt een deel al als vraag (drie markeringen in run 1), en de
grens met een gewone vraag was bij het labelen de minst scherpe van alle
soorten: "kan de minister ons daarover informeren" is een vraag, met "vóór de
begrotingsbehandeling" erbij een verzoek om een brief. Vier van de tien zijn
onzeker. Een eigen soort geeft twee draadjes voor wat één verzoek is. Maak er
een veld op de vraag van ("vraagt om een brief of overzicht", met het moment
als dat genoemd wordt) en toon het in de regel van de vraag. Als toezeggingen
er zijn, is dat veld ook wat een toezegging aan een verzoek koppelt.

Als het later toch een soort wordt: alleen een Kamerlid, en in het citaat een
zelfstandig naamwoord voor het stuk (brief, overzicht, rapportage, schriftelijk)
of "de Kamer informeren" met een moment.

### feitelijke_claim: niet toevoegen

**Definitie zoals gelabeld.** Een bewering met een concreet getal of een datum
over de wereld of over beleid, die een ministerie zou willen controleren.

**In de set.** 54 zeker, 11 onzeker, 9,3 per uur. Dat is met een smalle
definitie. 52 komen van Kamerleden, 13 van een bewindspersoon. In één termijn
van vier minuten stonden er zes.

**Waarom niet.** Welke van de zes een ministerie iets kan schelen is uit het
transcript niet op te maken; het hangt af van wat het ministerie al weet. Ik
schat dat een tweede labeller het bij een derde niet met mij eens zou zijn, en
dan is er geen gouden set om een prompt op te meten. Getallen zijn bovendien
wat de ondertiteling het slechtst weergeeft. Negen markeringen per uur erbij,
bovenop 23 vragen, maakt het kanaal onleesbaar.

Wat wel zou kunnen, later: alleen cijfers die de eigen bewindspersoon noemt
(13 in deze set), als hulp voor wie het verslag corrigeert. Of een reactie
waarmee een ambtenaar zelf een zin als claim markeert.

## Volgorde

1. De twee controles in de code en de twee alinea's in de prompt, in die
   volgorde van belang. Meet opnieuw met `--compare` tegen de bewaarde baseline,
   twee runs.
2. De namen van de initiatiefnemers in de context.
3. Motie als soort.
4. Toezegging als soort, met de lijst van de voorzitter als bevestiging.
5. "Vraagt om een brief" als veld op de vraag.
6. Geen feitelijke claims.

## Wat onzeker is

- Eén labeller. 39 van de 266 items zijn onzeker gelabeld.
- Het model in productie kan een ander zijn dan het gemeten model.
- De beurten zijn op tijd alleen toegewezen. Het tweede productievoorbeeld
  (een Kamerlid dat tegen een collega iets over het kabinet zegt) kwam daardoor
  in de beurt van de voorzitter terecht en is niet aan het model voorgelegd.
  Het zit wel in de gouden set en in de fixture.
- Twee runs per variant is te weinig om een verschil van een paar punten vast
  te stellen. De controles in de code hebben dat probleem niet: die zijn op
  dezelfde antwoorden van het model toegepast.
- Het aantal eerder aangenomen moties dat wordt genoemd (ten minste 8) is een
  telling achteraf, geen label.
