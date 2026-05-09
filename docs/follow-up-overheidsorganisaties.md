# Vervolg-werk na Overheidsorganisaties-PR

Wat in deze PR is gebouwd (na 4 review-rondes):

- **TOOI-spine**: ~1500 NL-overheidsorganisaties uit 8 `rwc_*` waardelijsten
- **Ministeries.csv** (OIN, FTE, organogram-link), **RIO email-domeinen** (~5000)
- **Organogram-scrape** voor 9 ministeries (DG/directie-laag, ~90 rijen) met
  type-classificatie (cluster, agentschap, overig, etc.)
- **TK + EK kamerleden**: 133 actieve TK-leden via FractieZetelPersoon met
  echte van/tot-datum + 84 EK-leden via Persoon-entity
- **Kabinet-Jetten** scrape via rijksoverheid.nl: ~28 bewindspersonen, met
  auto-heractivering van TOOI-soft-deleted ministeries
- **Historische kabinetten**: kabinet-Schoof in `kabinetten_historisch.yaml`
  met van/tot-data per bewindspersoon (Eddie van Marum verloop-fix)
- **ABD-benoemingen-scrape** via Playwright: leest
  algemenebestuursdienst.nl/actueel/nieuws en koppelt SG/DG-/directeur-
  benoemingen aan TOOI-organisaties
- **ExterneOrganisatie volledig vervangen** door OrganisatieEenheid
  (~79 referenties + tabel + 50 testfuncties hertest)
- **Synthetische groep-nodes** (12 stuks: HCvS, Rechtspraak, OM, Gemeenten,
  Provincies, Waterschappen, Samenwerking, BES, ZBO's, Marktpartijen,
  Internationale organisaties, Onderwijsinstellingen)
- **Admin sync-trigger endpoints** voor alle syncs + cron in worker (24h)
- **Reconciliation REST-API + UI in Beheer** (Beheer > Reconciliatie)
- **Email→organisatie endpoint + UI-suggestie** bij persoon-aanmaak
- **Mutatie-blokkade** voor bron != 'handmatig' rijen
- **Soft-deleted toggle** + bron-specifieke badges (TOOI, Scrape, FCC) met
  tooltip
- **Sync-alert notificaties** naar super_admins bij sanity-skip of conflicts
- **Person-deduplicatie** tussen TK + kabinet
- **Wikidata QID-veld** op Person voor toekomstige cross-link
- **1076 backend tests groen, 0 skipped** — geen test-debt

## Wat nog open kan blijven (echt vervolg-PR)

### Personen / rollen

- [ ] **Burgemeesters/wethouders/gedeputeerden/dijkgraven**: geen open API
      met SLA. VNG ledendatabank niet publiek. Voor nu skippen.
- [ ] **TK ex-Kamerleden** (`Functie='Oud Kamerlid'`) als pre-fetch om
      bewindspersoon-fuzzy-match te verbeteren. Veroorzaakt forse DB-groei
      (~3000 oud-kamerleden).
- [ ] **Wikidata QID auto-vulling**: SPARQL-query op huidige Person-namen
      tegen Wikidata cabinet-of-NL Q-items. YAGNI tot profiel-foto-feature
      relevant wordt.
- [ ] **COR-CSV decentraal OIN**: portaal.digikoppeling.nl was offline tijdens
      build; check later voor decentraal OIN-koppeling op gemeenten/ZBO's.

### Data-kwaliteit

- [ ] **ABD-scrape match-rate** verhogen: 6/10 nu, 4 mislukken door
      'de Belastingdienst' / 'OCWAstrid' patroon. Body parsing verbeteren
      door direct de detail-pagina van het nieuws te scrapen ipv lijst-tekst.
- [ ] **Allmanak.nl** als verrijking voor DG-rolverdeling (eerdere check
      gaf lege array; mogelijk authn nodig).

### Operations

- [ ] **Schedule fine-tuning**: nu draait worker dagelijks om 04:00.
      Strakker: TOOI dagelijks, organogram wekelijks, kabinet wekelijks,
      ABD dagelijks (continue benoemingen-feed).
- [ ] **Playwright in productie**: Dockerfile installeert chromium-headless-shell;
      check of dat in zad-deployment werkt. Optioneel: dedicated worker-pod
      voor browser-scrapes.

### Scope-uitbreidingen

- [ ] **Universiteiten/hogescholen** vullen via DUO-register
      (BRIN-codes + namen). Synthetische 'Onderwijsinstellingen'-groep
      bestaat al.
- [ ] **Marktpartijen verrijking**: KvK-koppeling voor 'Marktpartijen en
      overige'-rijen (commerciële licentie nodig).
