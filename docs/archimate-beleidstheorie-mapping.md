# ArchiMate Motivation Extension — Beleidstheorie Mapping

Dit document beschrijft de conceptuele mapping tussen ArchiMate (Motivation Extension) en de Beleidstheorie/Beleidskompas terminologie, en hoe Bouwmeester beide taalwerelden bedient.

## Context

Bureau Architectuur Digitale Overheid en beleidsmedewerkers beschrijven dezelfde causale keten — waarom we dingen doen, wat we willen bereiken, via welke interventies — maar in verschillende taalwerelden:

- **Architecten**: ArchiMate Motivation Extension (Driver, Goal, Principle, Capability, etc.)
- **Beleidsmakers**: Beleidstheorie/Beleidskompas (Probleem, Doel, Beleidskader, Instrument, etc.)

---

## A. Conceptmapping

| ArchiMate (Motivation) | Beleidstheorie / Beleidskompas | In Bouwmeester? | Bouwmeester node_type |
|---|---|---|---|
| Driver | Probleem / Aanleiding | Ja | `probleem` |
| Assessment | Probleemanalyse (stap 1) | Nee | Metadata op `probleem` |
| Stakeholder | Doelgroep / Actor | Deels | `Person` + `NodeStakeholder` (doelgroep als doelpubliek ontbreekt) |
| Goal | Doel (strategisch/specifiek) | Ja | `doel` |
| Outcome | Effect (outcome/impact) | Ja | `effect` |
| Principle | Beleidsuitgangspunt / Beleidskader | Ja | `beleidskader` |
| Requirement | Randvoorwaarde / Vereiste | Nee | Alleen als edge type `vereist` |
| Constraint | Beperking / Kader | Nee | Kan samenvallen met randvoorwaarde |
| Value | Maatschappelijke waarde | Nee | Toekomstige uitbreiding |
| Meaning | Beleidstheorie | Nee | Metadata/beschrijving op dossier |
| Course of Action | Beleidsoptie | Ja | `beleidsoptie` |
| Capability | Instrument | Ja | `instrument` |
| Resource | Middelen (budget, fte) | Nee | Alleen `kosten_indicatie` tekstveld op maatregel |

### Toelichting

- **Driver / Probleem**: Het "waarom" dat alles aandrijft. In ArchiMate een externe of interne factor; in beleidstheorie het maatschappelijk probleem.
- **Goal / Doel**: Direct equivalent. ArchiMate onderscheidt niet expliciet tussen strategisch en operationeel, Bouwmeester wel via het `type` veld.
- **Outcome / Effect**: ArchiMate's Outcome beschrijft het resultaat van architectuurwerk. In beleidstheorie is dit de resultaatketen: output → outcome → impact.
- **Principle / Beleidskader**: ArchiMate-principes zijn richtinggevende uitspraken; beleidskaders zijn het juridisch en beleidsmatig kader. Voldoende overlap voor mapping.
- **Course of Action / Beleidsoptie**: Beide beschrijven een mogelijke aanpak voordat een keuze is gemaakt.
- **Capability / Instrument**: ArchiMate's Capability is het vermogen van de organisatie; een beleidsinstrument is het middel waarmee beleid wordt uitgevoerd. Functioneel equivalent.
- **Maatregel**: Geen direct ArchiMate-equivalent. Bouwmeester-specifiek als concrete uitvoeringsmaatregel, mapped naar `CourseOfAction` met status "gekozen" bij export.

---

## B. Edge Type Mapping

| Bouwmeester edge | ArchiMate relatie | Richting | Notities |
|---|---|---|---|
| `draagt_bij_aan` | Influence | source → target | Positieve bijdrage |
| `implementeert` | Realization | source realizes target | Instrument/maatregel realiseert doel |
| `kadert` | Association / Composition | bidirectional | Beleidskader kadert doel/instrument |
| `vereist` | Serving / Access | source serves target | Randvoorwaarde |
| `conflicteert_met` | *(geen equivalent)* | bidirectional | Bouwmeester-specifiek |
| `vervangt` | *(geen equivalent)* | source → target | Lifecycle management |
| `aanvulling_op` | Aggregation | source → target | Deels |
| `leidt_tot` | Triggering | source triggers target | Causale keten: probleem→doel, maatregel→effect |
| `adresseert` | Influence (negatief) | source → target | Maatregel/instrument adresseert probleem |
| `meet` | Association | source → target | Effect wordt gemeten aan indicator/doel |

### Ontbrekende ArchiMate-relaties

- **Composition**: Niet expliciet nodig; dossier fungeert als container.
- **Specialization**: Niet relevant voor het huidige model.
- **Flow**: Kan relevant worden bij procesmodellering (toekomstig).

---

## C. Resultaatketen (Gap-analyse)

Zowel ArchiMate's motivation→strategy→business keten als beleidstheorie's interventie→output→outcome→impact keten waren niet volledig gemodelleerd.

### Huidige situatie (voor deze release)

Bouwmeester had `doel` (wat we willen) en `maatregel` (wat we doen), maar geen manier om te modelleren:

1. Welk **probleem** een dossier motiveert
2. Welke **output** een maatregel produceert
3. Welk **outcome** die output oplevert
4. Welke maatschappelijke **impact** dat creëert
5. De causale theorie die ze verbindt

### Oplossing

Met de toevoeging van `probleem`, `effect` (met type output/outcome/impact) en `beleidsoptie` kan de volledige keten worden gemodelleerd:

```
probleem ──leidt_tot──→ doel
                          ↑
beleidsoptie ──draagt_bij_aan──→ doel
                          ↓
           maatregel ──implementeert──→ doel
                          │
                    ──leidt_tot──→ effect (output)
                                      │
                                ──leidt_tot──→ effect (outcome)
                                                    │
                                              ──leidt_tot──→ effect (impact)
                                                    │
                                              ──meet──→ doel (streefwaarde)
```

---

## D. Aanbevelingen en Prioritering

Prioritering van ontbrekende concepten op basis van waarde voor beide doelgroepen:

| # | Concept | ArchiMate | Status | Rationale |
|---|---------|-----------|--------|-----------|
| 1 | `probleem` | Driver | **Geimplementeerd** | Het "waarom" dat alles verankert |
| 2 | `effect` | Outcome | **Geimplementeerd** | Sluit de resultaatketen |
| 3 | `beleidsoptie` | Course of Action | **Geimplementeerd** | Maakt vergelijking van alternatieven mogelijk |
| 4 | `randvoorwaarde` | Requirement/Constraint | Toekomstig | Legt beperkingen vast als eerste-klas objecten |
| 5 | `waarde` | Value | Toekomstig | Beschrijft de maatschappelijke waardepropositie |
| 6 | `doelgroep` | Stakeholder | Toekomstig | Doelpubliek als apart concept (nu via NodeStakeholder) |

### Toekomstige uitbreidingen

- **Resource-modellering**: Budget, fte, en andere middelen als eerste-klas objecten
- **Procesmodellering**: ArchiMate Business Layer integratie voor uitvoeringsprocessen
- **Meervoudige taxonomieen**: Ondersteuning voor TOGAF, NORA en andere raamwerken naast ArchiMate
