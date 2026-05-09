"""Auto-vul Person.wikidata_qid via Wikidata SPARQL.

Query: alle huidige Tweede Kamerleden (P39 = Q19952078) en bewindspersonen.
Match op naam-equivalentie (rdfs:label nl/en) tegen Person.naam.

CC0 (Wikidata-data is CC0). Beste-effort match; als naam niet uniek of niet
in Wikidata staat blijft `wikidata_qid` NULL.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.person import Person

log = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# P39 (position held) Q-id's voor relevante NL-functies
QUERY_TK_LEDEN = """
SELECT ?person ?personLabel WHERE {
  ?person p:P39 ?stmt .
  ?stmt ps:P39 wd:Q19952078 .
  FILTER NOT EXISTS { ?stmt pq:P582 ?endTime . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "nl,en". }
}
"""

QUERY_BEWINDSPERSONEN_NL = """
SELECT ?person ?personLabel WHERE {
  ?person p:P39 ?stmt .
  VALUES ?function {
    wd:Q83307            # minister
    wd:Q4493881          # staatssecretaris
    wd:Q373085           # minister-president
  }
  ?stmt ps:P39 ?function .
  FILTER NOT EXISTS { ?stmt pq:P582 ?endTime . }
  ?person wdt:P27 wd:Q29 .  # NL-staatsburger
  SERVICE wikibase:label { bd:serviceParam wikibase:language "nl,en". }
}
"""


@dataclass
class WikidataSyncStats:
    sync_run_id: uuid.UUID
    matches: int = 0
    geen_match: int = 0
    api_fouten: list[str] = field(default_factory=list)


async def _query_sparql(query: str, *, timeout: float = 30.0) -> list[dict]:
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": (
            "Bouwmeester/1.0 (https://github.com/BureauArchitectuurDigitaleOverheid"
            "/bouwmeester) bouwmeester@example.com"
        ),
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            WIKIDATA_SPARQL,
            params={"query": query},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("results", {}).get("bindings", [])


def _qid_uit_uri(uri: str) -> str | None:
    """http://www.wikidata.org/entity/Q33181 -> Q33181."""
    if not uri.startswith("http://www.wikidata.org/entity/"):
        return None
    return uri.rsplit("/", 1)[-1]


async def sync_wikidata_qid(
    session: AsyncSession,
    *,
    commit: bool = True,
) -> WikidataSyncStats:
    """Run Wikidata SPARQL queries en match op Person.naam.

    Bij match: schrijft Person.wikidata_qid. Idempotent — bestaande QIDs
    worden niet overschreven (handmatige overrides blijven).
    """
    sync_run_id = uuid.uuid4()
    stats = WikidataSyncStats(sync_run_id=sync_run_id)

    # Pak Person-rijen die nog geen QID hebben
    rows = (
        (await session.execute(select(Person).where(Person.wikidata_qid.is_(None))))
        .scalars()
        .all()
    )
    naam_naar_person: dict[str, Person] = {p.naam: p for p in rows}

    # Combineer beide queries
    qids_per_naam: dict[str, str] = {}
    for query in (QUERY_TK_LEDEN, QUERY_BEWINDSPERSONEN_NL):
        try:
            results = await _query_sparql(query)
        except Exception as exc:  # noqa: BLE001
            stats.api_fouten.append(str(exc)[:200])
            continue
        for row in results:
            uri = row.get("person", {}).get("value", "")
            label = row.get("personLabel", {}).get("value", "")
            qid = _qid_uit_uri(uri)
            if not qid or not label:
                continue
            qids_per_naam.setdefault(label, qid)

    # Match
    for naam, qid in qids_per_naam.items():
        person = naam_naar_person.get(naam)
        if person is None:
            continue
        person.wikidata_qid = qid
        stats.matches += 1

    stats.geen_match = len(rows) - stats.matches

    if commit:
        await session.commit()
    else:
        await session.flush()
    log.info(
        "Wikidata QID sync run=%s: %d matches, %d zonder match, %d api-fouten",
        sync_run_id,
        stats.matches,
        stats.geen_match,
        len(stats.api_fouten),
    )
    return stats
