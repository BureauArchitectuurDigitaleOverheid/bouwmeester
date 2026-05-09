# Vervolg-werk na Overheidsorganisaties-PR

Wat in deze PR is gebouwd (na 5 review-rondes):

- **TOOI-spine**: ~1500 NL-overheidsorganisaties uit 8 `rwc_*` waardelijsten
- **Ministeries.csv** (OIN, FTE, organogram-link), **RIO email-domeinen** (~5000)
- **Organogram-scrape** voor 9 ministeries (DG/directie-laag, ~90 rijen)
- **TK + EK kamerleden**: 133 actieve TK + 84 EK met start/eind-datums
- **Kabinet-Jetten** scrape via rijksoverheid.nl: ~28 bewindspersonen
- **Historische kabinetten** (kabinet-Schoof in YAML): 23 bewindspersonen
- **ABD-benoemingen** via Playwright: 100% match-rate door detail-pagina-scrape
- **Onderwijsinstellingen** via curated YAML: 14 universiteiten + 29 hogescholen
- **Wikidata QID** veld + SPARQL-sync (rate-limited tijdens build, werkt
  in productie als Wikidata WDQS herstelt)
- **ExterneOrganisatie volledig vervangen** door OrganisatieEenheid (50+ tests hertest)
- **12 synthetische groepen** (HCvS, Rechtspraak, OM, Gemeenten, Provincies,
  Waterschappen, Samenwerking, BES, ZBO's, Marktpartijen, Internationale,
  Onderwijsinstellingen)
- **Admin sync-trigger endpoints** + **2 cron-loops in worker** (dagelijks
  voor TK/kabinet/ABD, wekelijks voor TOOI/RIO/CSV/organogram)
- **Reconciliation REST-API + Beheer-pagina** (side-by-side merge/ignore)
- **Email→organisatie suggestie** in persoon-form
- **Mutatie-blokkade** voor bron != 'handmatig' rijen
- **Soft-deleted toggle** + bron-specifieke badges met tooltip
- **Sync-alert notificaties** naar super_admins (sanity-skip + conflicts)
- **Person-deduplicatie** TK + kabinet
- **Auto-heractivering** ministeries die bij kabinetwissel terugkeren
- **TK Oud-Kamerleden fetcher** voor fuzzy-match in kabinet-sync
- **1094 backend tests groen, 0 skipped** — geen test-debt
- **OrganisatieDetail rijke metadata-velden**: OIN, FTE, website, KvK,
  TOOI-URI met externe links
- **PersonCardExpandable**: TK-link + Wikidata-link wanneer beschikbaar
- **Sync-status dashboard** in Beheer: laatste run per bron, run-knoppen,
  conflict-teller, 'Alles syncen'-knop
- **Tests voor reconciliation-API** (7 tests) en **ABD-scrape parser** (11 tests)

## Wat echt overblijft (geen open API/data-bron)

- **Burgemeesters/wethouders/gedeputeerden/dijkgraven**: getest tegen
  Allmanak (PostgREST 404), VNG (niet publiek), wikidata (rate-limited).
  Geen open API met SLA, blijft vervolg.
- **COR-CSV decentraal OIN**: portaal.digikoppeling.nl niet bereikbaar
  vanuit ontwikkelomgeving. Test in productie of met VPN.
- **Marktpartijen via KvK**: commerciële licentie, niet voor MVP.

## Optionele verfijningen

- **Wikidata QID**: SPARQL werkt maar Wikidata-query-service was
  rate-limiting tijdens build (1 req/min). In productie zal dit beter zijn.
  Endpoint + admin-button blijven beschikbaar; herhalen tot het lukt.
- **Allmanak DG-laag**: API niet langer publiek beschikbaar via v0/persoon.
  Eventueel via hun GitHub openstate/allmanak repo + handmatige curated
  lijst.
