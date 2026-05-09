# Vervolg-werk na Overheidsorganisaties-PR

Wat in deze PR is gebouwd (na review-rondes):

- TOOI-spine: ~1500 NL-overheidsorganisaties uit 8 `rwc_*` waardelijsten
- Ministeries.csv (OIN, FTE, organogram-link), RIO email-domeinen (~5000)
- Organogram-scrape voor 9 ministeries (DG/directie-laag, ~90 rijen) met
  type-classificatie op basis van naam (cluster, agentschap, overig, etc.)
- TK OData FractieZetelPersoon: 133 actieve TK-leden met echte van/tot-datum
- TK OData Persoon: 84 actieve EK-leden gekoppeld aan synthetische 'Eerste Kamer'
- Kabinet-Jetten scrape via rijksoverheid.nl: ~28 bewindspersonen, met
  auto-heractivering van TOOI-soft-deleted ministeries als rijksoverheid.nl
  ze nog toont
- Auto-merge persoon bij naam-match (kabinet-bewindspersonen die ex-TK-lid zijn)
- Dedupe-script voor handmatige duplicates
- ExterneOrganisatie volledig vervangen door OrganisatieEenheid
- Synthetische groep-nodes (HCvS, Rechtspraak, OM, Gemeenten, Provincies,
  Waterschappen, Samenwerkingsorganisaties, Caribische openbare lichamen,
  ZBO's en agentschappen, Marktpartijen en overige)
- Admin sync-trigger endpoints + cron in worker (24h default)
- Reconciliation REST-API (GET/merge/ignore)
- Email->organisatie-match endpoint voor RIO-suggestie bij persoon-aanmaak
- Mutatie-blokkade: bron != 'handmatig' rijen zijn read-only (alleen super_admin)
- UI met collapse-default voor synthetische groepen + zoekveld + TOOI-badge
- Synthetische groepen worden door de Alembic-migratie aangemaakt (idempotent
  via NOT EXISTS) zodat fresh deploys ze direct hebben.
- Mutatie-blokkade getest: TOOI/synthetische rijen weigeren updates voor
  non-super_admin (3 nieuwe tests in `test_organisatie.py`).

## Wat nog moet komen

### Personen / rollen — uitbreidingen

- [ ] **ABD topmanagementgroep wie-is-wie** (algemenebestuursdienst.nl):
      SG/DG-namen koppelen aan bestaande DG-rijen. Pagina is een Next.js SPA;
      vereist headless browser-scrape (Playwright). Update-frequentie laag.
      Voorstel: maandelijkse Playwright-scrape, fallback handmatige YAML.
- [ ] **TK ex-Kamerleden met functie='Oud Kamerlid'**: bewindspersonen met
      TK-historie kunnen gevonden worden door op naam achternaam te zoeken.
      Nu doet de kabinet-sync een fuzzy match maar die werkt alleen als de
      Person al in de DB zit. Vooraf alle Oud Kamerleden inlezen zou werken
      maar veroorzaakt forse DB-groei.
- [ ] **Burgemeesters/wethouders/gedeputeerden/dijkgraven**: geen open API
      met SLA. VNG ledendatabank niet publiek. Voor nu skippen.
- [ ] **Historische kabinetten in YAML**: nu alleen huidig kabinet. Voor
      historische correctheid alle kabinetten Rutte I-IV en Schoof
      importeren met historische van/tot-data.

### UI-features

- [ ] **Reconciliation UI in Beheer**: backend-endpoints zijn klaar
      (`GET /api/admin/reconciliation`, `POST .../merge`, `POST .../ignore`).
      Frontend page met side-by-side handmatig vs TOOI-kandidaat.
- [ ] **RIO email-suggestie UI**: backend `GET /api/people/match-email-organisatie?email=...`
      is klaar. Frontend: bij persoon-form-email-veld onChange aanroepen en
      "Wil je deze persoon koppelen aan X?"-prompt tonen.
- [ ] **Soft-deleted weergave**: `OrganisatieEenheid.geldig_tot != NULL` rijen
      worden nu volledig gefilterd uit de tree. Optie: 'Toon historisch'
      toggle om verlopen rijen grijs/doorgestreept te tonen.
- [ ] **TOOI-badge styling**: het badge zegt nu "TOOI" met grijze achtergrond.
      Kan visueel beter (icoon + tooltip met bron-uitleg).

### Tests

- [ ] **Hertest `test_opdrachten.py`, `test_fcc_sync.py`, `test_graph.py`**:
      drie testbestanden geskipt (refereren naar verwijderde
      `ExterneOrganisatie`). Herschrijven naar OrganisatieEenheid-aanpak.
- [ ] **Test_tooi_sync.py is geschreven maar geskipt**: sync-services doen
      eigen `session.commit()` wat de transaction-rollback van db_session
      breekt. Vervolg: geïsoleerde test-DB-fixture of `commit=False`-flag
      in services.
- [ ] **Tests voor merge_existing_with_tooi.py, kabinet_scrape.py
      ministerie-detectie, RIO XML parser**: nu alleen end-to-end
      gevalideerd via lokale runs.

### Data-kwaliteit

- [ ] **Allmanak.nl als verrijking**: PostgREST endpoint met SG/DG-personen
      (eerdere check gaf lege array, mogelijk authn nodig). Test live.
- [ ] **OIN-verrijking decentraal**: COR-CSV
      (`data.overheid.nl/dataset/centrale-oin-raadpleegvoorziening-cor`)
      joinen op naam/KvK voor gemeenten/ZBO's.
- [ ] **Wikidata cross-link op personen**: optioneel veld `wikidata_qid`
      toevoegen voor toekomstige verrijking (foto, partij-historie via
      SPARQL). YAGNI tot profielfoto-feature relevant wordt.

### Operations

- [ ] **Reconciliation-notificaties**: als `pending_reconciliation` na sync
      meer dan N rijen heeft, stuur notification naar super_admins.
- [ ] **Sanity-check observability**: `sync_tooi.skipped_sanity=True` moet
      een loud signal zijn (Slack/Mattermost), nu alleen log.
- [ ] **Schedule fine-tuning**: nu draait worker dagelijks om 04:00 (default
      24h). Strakker: TOOI dagelijks, organogram wekelijks (mutaties
      zeldzaam), kabinet ook wekelijks.

### Scope-uitbreidingen

- [ ] **Internationale overheden**: voor stakeholders bij EU-instellingen,
      OECD, etc. Synthetische groep "Internationaal" + handmatige
      toevoegingen.
- [ ] **Universiteiten/hogescholen**: niet in TOOI. DUO heeft een register.
- [ ] **Marktpartijen verrijking**: KvK-koppeling voor 'Marktpartijen en
      overige'-rijen (commerciële licentie). Niet voor MVP.
