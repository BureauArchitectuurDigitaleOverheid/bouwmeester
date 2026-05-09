# Vervolg-werk na Overheidsorganisaties-PR

Wat in deze PR is gebouwd:

- TOOI-spine: 1438 NL-overheidsorganisaties uit 8 `rwc_*` waardelijsten
- Ministeries.csv (OIN, FTE, organogram-link), RIO email-domeinen (~5000)
- Organogram-scrape voor 8 ministeries (DG/directie-laag, ~90 rijen)
- TK OData kamerleden (133 actieve TK-leden met echte van/tot-datum)
- Kabinet-Jetten scrape via rijksoverheid.nl (~25 bewindspersonen)
- ExterneOrganisatie volledig vervangen door OrganisatieEenheid
- Synthetische groep-nodes (HCvS, Rechtspraak, OM, Gemeenten, etc.)
- Admin sync-trigger endpoints + cron in worker
- UI met collapse-default voor synthetische groepen + zoekveld + TOOI-badge

## Wat nog moet komen

### Personen / rollen — uitbreidingen

- [ ] **ABD topmanagementgroep wie-is-wie** (algemenebestuursdienst.nl): SG/DG-namen koppelen aan
      bestaande DG-rijen. Pagina is een Next.js SPA — vereist headless
      browser-scrape (Playwright). Werkt niet met simpele HTTP-fetch.
      Update-frequentie: laag (paar keer per jaar). Voorstel: maandelijkse
      Playwright-scrape, fallback handmatig YAML.
- [ ] **Eerste Kamer leden**: TK OData levert `Persoon.Functie='Eerste Kamerlid'`
      maar geen `FractieZetelPersoon`-equivalent. Aparte sync schrijven die
      gewoon op `Persoon` zelf filtert (zonder van/tot — die info ontbreekt
      in OData).
- [ ] **Burgemeesters/wethouders/gedeputeerden/dijkgraven**: geen open API met
      SLA. VNG ledendatabank niet publiek. Voor nu skippen.
- [ ] **Bewindspersonen-portefeuilles voor nieuwe ministeries**: Asiel & Migratie,
      Klimaat & Groene Groei, Volkshuisvesting & RO werden door TOOI als
      `geldig_tot=2026-02-22` gemarkeerd. Kabinet-Jetten heeft ze weer. De
      kabinet-scraper logt dit als 'niet matchde'. Strakkere oplossing: bij
      kabinet-scrape, als ministerienaam matcht in `MINISTERIE_ALIAS` maar
      TOOI-rij `geldig_tot` heeft, automatisch heractiveren (`geldig_tot=NULL`).

### UI-features

- [ ] **Reconciliation UI in Beheer**: tabel `pending_reconciliation` heeft rijen
      maar geen UI om ze handmatig op te lossen. Bouwen: lijst-view met
      side-by-side handmatig vs TOOI-kandidaat, knop 'Mergen' / 'Negeren'.
- [ ] **RIO email-domein-suggestie bij persoon-aanmaak**: als iemand persoon
      met email `@cjib.nl` invoert, toon "Wil je deze persoon koppelen aan
      CJIB?". Data zit al in `organisatie_email_domein`. Frontend-only
      feature.
- [ ] **Soft-deleted weergave**: `OrganisatieEenheid.geldig_tot != NULL` rijen
      moeten in UI grijs/doorgestreept tonen onder een 'Toon historisch'-toggle.
      Nu zijn ze gewoon zichtbaar als levende rijen.
- [ ] **Mutatie-blokkade voor bron != handmatig**: het plan beloofde dat
      TOOI-rijen read-only zijn voor naam/parent/type. Backend-check ontbreekt
      nog. Toevoegen aan `_check_eenheid_write_access` in
      `routes/organisatie.py`.
- [ ] **TOOI-badge styling**: het badge zegt nu "TOOI" met grijze achtergrond.
      Kan visueel beter (icoon + tooltip met bron-uitleg).

### Tests

- [ ] **Hertest `test_opdrachten.py`, `test_fcc_sync.py`, `test_graph.py`**:
      drie testbestanden zijn geskipt omdat ze nog naar verwijderde
      `ExterneOrganisatie` refereren. Herschrijven naar OrganisatieEenheid-
      aanpak. ~50 testfuncties.
- [ ] **Testdekking voor sync-services**: `test_tooi_sync.py`, `test_rio_sync.py`,
      etc. met mock-fetchers. Nu alleen end-to-end gevalideerd via lokale runs.
- [ ] **Test voor `merge_existing_with_tooi.py`**: edge-case waar twee
      ministeries dezelfde TOOI-naam zouden krijgen.
- [ ] **Test voor `kabinet_scrape.py` ministerie-detectie**: regex moet alle
      bekende portefeuilles dekken; nu 4-van-28 niet-matched.

### Data-kwaliteit

- [ ] **Type-classificatie organogram-scrape**: scraper labelt alle DG-pagina's
      als `directoraat_generaal`, ook als ze duidelijk een Cluster, Diensten,
      Commissie of Politieke leiding zijn. H1/h2-tekst pattern-detectie
      toevoegen.
- [ ] **Allmanak.nl als verrijking voor DG-rolverdeling**: PostgREST endpoint
      met SG/DG-personen (mits live-test slaagt; eerdere check gaf lege
      array, mogelijk authn nodig).
- [ ] **OIN-verrijking decentraal**: COR-CSV
      (`data.overheid.nl/dataset/centrale-oin-raadpleegvoorziening-cor`)
      joinen op naam/KvK voor gemeenten/ZBO's.
- [ ] **Wikidata cross-link op personen**: optioneel veld `wikidata_qid` toevoegen
      voor toekomstige verrijking (foto, partij-historie via SPARQL).
      YAGNI-besluit was 'niet nu'; herzien wanneer profiel-foto-feature
      relevant wordt.

### Kabinet-yaml en historische data

- [ ] **Kabinet-yaml gevuld met historische kabinetten**: nu staat alleen
      huidig in YAML; verlaten functies krijgen `eind_datum=today` bij
      verwijdering. Voor historische correctheid: alle kabinetten Rutte
      I-IV en Schoof importeren met historische van/tot-data.
- [ ] **Auto-heractivering ministeries**: bij kabinetwissel kunnen oude
      ministeries terugkomen (zie boven). Heuristiek toevoegen aan
      `kabinet_scrape.py`.

### Operations

- [ ] **Reconciliation-notificaties**: als `pending_reconciliation` na sync
      meer dan N rijen heeft, stuur notification naar super_admins.
- [ ] **Sanity-check observability**: `sync_tooi.skipped_sanity=True` moet
      een loud signal zijn (Slack/Mattermost), nu alleen log.
- [ ] **Schedule fine-tuning**: nu draait worker dagelijks om 04:00 (default
      24h). Kan strakker: TOOI dagelijks, organogram wekelijks (mutaties
      zeldzaam), kabinet ook wekelijks.

### Scope-uitbreidingen

- [ ] **Internationale overheden**: voor stakeholders bij EU-instellingen,
      OECD, etc. Apart synthetische groep onder de boom of aparte tabel.
- [ ] **Marktpartijen verrijking**: KvK-koppeling voor `Marktpartijen en
      overige`-rijen (commerciële licentie). Niet voor MVP.
