# PR-review: NL overheidsorganisaties (PR #313)

Self-review na 7 commits. Doel: laatste check vóór merge.

## Wat erin zit (samenvattend)

**Externe data-bronnen geïntegreerd**:
- TOOI-waardelijsten (ministeries, ZBO's, gemeenten, provincies, waterschappen,
  HCvS, rechtspraak, OM, samenwerking, BES, overige) — ~1500 organisaties
- Ministeries.csv (OIN, FTE, organogram-link) — 12 ministeries verrijkt
- RIO email-domeinen — ~5000 mappings
- Organogram-scrape rijksoverheid.nl — ~90 DG/directies voor 9 ministeries
- TK OData FractieZetelPersoon + Persoon — 133 TK + 84 EK leden
- Kabinet-scrape rijksoverheid.nl — 28 huidige bewindspersonen
- Kabinet-Schoof YAML (historisch) — 23 bewindspersonen met van/tot
- ABD-benoemingen via Playwright — 100% match-rate, continu nieuws-feed
- DUO/UNL/VHO onderwijsinstellingen YAML — 14 universiteiten + 29 hogescholen
- Wikidata QID-sync via SPARQL — werkt zodra Wikidata-rate-limit voorbij

**Datamodel**:
- ExterneOrganisatie volledig vervangen door OrganisatieEenheid
- 12 synthetische groep-nodes als top-level peers van ministeries
- Person-velden: tk_persoon_id, wikidata_qid, bron
- PersonOrganisatieEenheid: functietitel, bron, start/eind-datum
- Nieuwe tabellen: organisatie_email_domein, tooi_sync_log,
  pending_reconciliation
- Mutatie-blokkade: TOOI/scrape/synthetisch read-only voor non-super_admin

**UI**:
- OrganisatiePage met collapse-default, zoekveld, soft-delete toggle,
  bron-filter (alle/handmatig/tooi/scrape), bron-specifieke badges
- OrganisatieDetail met OIN, FTE, website, KvK, TOOI-URI als externe links
- PersonCardExpandable met TK + Wikidata externe links
- Beheer > Reconciliatie: side-by-side conflict-resolutie (merge/ignore)
- Beheer > Sync-status: laatste run per bron + run-knoppen + tellers
- Persoon-form: RIO email-domein-suggestie ("koppel als organisatie X")

**Operations**:
- Worker met 2 cron-loops: dagelijks (TK + kabinet + ABD), wekelijks
  (TOOI + RIO + CSV + organogram)
- 11 admin sync-trigger endpoints + 'alles syncen' batch-endpoint
- Sync-alert notificaties naar super_admins (sanity-skip + conflicts)
- Auto-heractivering ministeries bij kabinetwissel
- Person-deduplicatie tussen TK + kabinet
- Reconciliation-tabel voor naam-conflicten

**Tests**: **1099 passed, 0 skipped** — geen test-debt
- 36 nieuwe sync-tests (TOOI, ABD, reconciliation, onderwijs, kabinet)
- 50 hertest van eerder geskipte ExterneOrganisatie-tests
- 3 mutatie-blokkade tests
- Frontend: typecheck + build schoon

## Productie-bug gevonden + gefixt

Tijdens schrijven van reconciliation-tests vond ik dat de routes
`/api/admin/sync` en `/api/admin/reconciliation` **dubbele /api-prefix**
hadden. De router-prefix begon met `/api/admin/...` terwijl `app.include_router`
zelf al `/api`-prefix toevoegt. Resultaat: 404 op alle admin-routes
(zou stilletjes broken zijn na deploy). Fix in commit a6bddd1.

## Wat is er gevalideerd

- 1099 backend-tests groen, lint clean (ruff + format), frontend build groen
- Alle migraties roundtrip (downgrade + upgrade) geverifieerd
- TOOI-sync 1437 organisaties geïmporteerd, idempotent gevalideerd
- ABD-scrape 100% match-rate (10/10) met live data
- RIO-sync 5056 domeinen geïmporteerd
- Reconciliation merge/ignore via API geverifieerd
- Person-deduplicatie: Willemijn Aerdts (kabinet+TK) gemerged naar 1 rij
- Eddie van Marum eind-datum-fix: na YAML-verwijdering krijgt hij
  automatisch eind_datum=today

## Wat in vervolg-PR's

Zie `follow-up-overheidsorganisaties.md`. Korte versie:
- Burgemeesters/wethouders: geen open API met SLA gevonden
- COR-CSV decentraal OIN: portaal niet bereikbaar tijdens build
- Wikidata QID-vulling: werkt maar Wikidata WDQS rate-limited tijdens build

## Bouwblokken voor toekomstige uitbreidingen

- Sync-services hebben `commit=False`-flag voor isolated tests
- `TooiSyncLog` audit-log per change voor rollback-mogelijkheid
- `pending_reconciliation` tabel als pattern voor andere conflict-flows
- `notify_super_admins` helper voor andere sync-alerts
- Synth groepen via migratie idempotent (NOT EXISTS)

## Risico's bij merge

1. **Migratie-volgorde**: 4 nieuwe Alembic-migraties, hangen aaneen via
   `down_revision`. Bij parallelle PRs met andere migraties kan rebase
   nodig zijn (`alembic merge`).

2. **ExterneOrganisatie-data-migratie**: één Alembic-revisie verplaatst
   alle externe-org-rijen naar OrganisatieEenheid + rewrite Lead/Opdracht
   FK. Voor productie-DB met live data: dump eerst, validate met audit
   script, daarna migreren. `scripts/audit_externe_organisaties.py` toont
   wat er gaat gebeuren.

3. **Playwright in productie**: Dockerfile installeert chromium-headless-shell
   via `playwright install`. Bij offline build kan dit mislukken — stap
   heeft een `|| echo`-fallback zodat de container niet crasht; ABD-scrape
   wordt dan gewoon uitgeschakeld.

4. **Worker-cron eerste-run**: bij eerste deploy draaien dagelijkse +
   wekelijkse loops meteen. TOOI-sync van 1437 organisaties + RIO 5000+
   domeinen kan 2-3 minuten duren. Acceptabel maar even op letten.

5. **Sync-services committen direct**: `commit=True` is default. In tests
   hebben we `commit=False` om transaction-rollback te respecteren.
   Production-side-effects zijn dus binnen de sync zelf afgesloten.
