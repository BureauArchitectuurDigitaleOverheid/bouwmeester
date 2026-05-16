"""TOOI-waardelijsten sync.

Haalt de acht `rwc_*_compleet` JSON-bestanden van standaarden.overheid.nl op
(KOOP/Logius), filtert historische versies eruit en upsert ze als
`OrganisatieEenheid` rijen. Parent-resolutie hangt elk type onder de juiste
synthetische groep (gemeenten -> 'Gemeenten', etc.) of onder een ministerie
voor ZBO/agentschap waar TOOI dat aangeeft.

Soft-delete: organisaties die uit de feed verdwijnen krijgen `geldig_tot=today`.
Conflict: wanneer een handmatige rij dezelfde naam heeft, schrijven we een
`pending_reconciliation` record en laten beide rijen bestaan -- mens beslist.

Sanity-check: de sync weigert door te gaan als hij meer dan 5% van bestaande
TOOI-rijen zou soft-deleten in een enkele run (mogelijk kapotte feed).
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.text import unescape_html
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)

WORK_BASE = "https://standaarden.overheid.nl/tooi/waardelijsten/work"
EXPRESSION_BASE = "https://standaarden.overheid.nl/tooi/waardelijsten/expression"
JSON_REPO = "https://repository.officiele-overheidspublicaties.nl/waardelijsten"

# De acht complete waardelijsten en de synthetische-groep-naam waaronder
# instanties die geen eigen ministerie-parent hebben moeten hangen.
RWC_LIJSTEN: tuple[tuple[str, str, str], ...] = (
    # (rwc_naam, default_type, synthetische_parent_naam)
    ("rwc_ministeries_compleet", "ministerie", None),
    ("rwc_zbo_compleet", "zbo", "ZBO's en agentschappen"),
    ("rwc_gemeenten_compleet", "gemeente", "Gemeenten"),
    ("rwc_provincies_compleet", "provincie", "Provincies"),
    ("rwc_waterschappen_compleet", "waterschap", "Waterschappen"),
    (
        "rwc_samenwerkingsorganisaties_compleet",
        "samenwerkingsorganisatie",
        "Samenwerkingsorganisaties",
    ),
    (
        "rwc_caribische_openbare_lichamen_compleet",
        "caribisch_openbaar_lichaam",
        "Caribische openbare lichamen",
    ),
    (
        "rwc_overige_overheidsorganisaties_compleet",
        "overig",
        "ZBO's en agentschappen",
    ),
)

# TOOI organisatiesoort-URIs (uit tooikern-thesaurus). Mapping naar onze
# eigen `type`-codes. Bron: organisaties.overheid.nl en TOOI-thesaurus.
# Onbekende soorten vallen terug op het default_type van de lijst.
ORGANISATIESOORT_NAAR_TYPE: dict[str, str] = {
    # Hoge Colleges van Staat zitten in rwc_overige_overheidsorganisaties.
    # We splitsen ze er handmatig uit obv naam-detectie hieronder.
}

# Naam-fragmenten binnen rwc_overige_overheidsorganisaties die duiden op een
# Hoge College van Staat / rechtspraak / OM. Hierop hangen we ze onder de
# juiste synthetische groep. Matching is case-insensitive substring.
# Vlaggen worden in volgorde gecheckt: HCvS > Rechtspraak > OM > overig.
HCVS_FRAGMENTEN = (
    "raad van state",
    "algemene rekenkamer",
    "nationale ombudsman",
    "kabinet van de koning",
    "tweede kamer",
    "eerste kamer",
    "staten-generaal",
)
RECHTSPRAAK_FRAGMENTEN = (
    "raad voor de rechtspraak",
    "hoge raad",
    "rechtbank",
    "gerechtshof",
    "centrale raad van beroep",
    "college van beroep voor het bedrijfsleven",
)
OM_FRAGMENTEN = (
    "openbaar ministerie",
    "arrondissementsparket",
    "landelijk parket",
    "functioneel parket",
    "ressortsparket",
    "parket-generaal",
    "parket bij de hoge raad",
)


@dataclass(frozen=True)
class TooiOrganisatie:
    """Geparseerde TOOI-rij (huidige versie, geen historisch)."""

    tooi_uri: str
    naam: str
    afkorting: str | None
    organisatiecode: str | None
    organisatiesoort: str | None
    einddatum: date | None
    rwc_lijst: str
    rwc_default_type: str
    rwc_default_parent_synth: str | None


# --- Fetching ---


async def _resolve_latest_json_url(client: httpx.AsyncClient, rwc_naam: str) -> str:
    """Vind de hoogste versie van een rwc-bestand via de work-pagina."""
    work_uri = f"https://identifier.overheid.nl/tooi/set/{rwc_naam}"
    resp = await client.get(WORK_BASE, params={"work_uri": work_uri})
    resp.raise_for_status()
    versies = re.findall(rf"{re.escape(rwc_naam)}%2F(\d+)", resp.text)
    if not versies:
        raise RuntimeError(f"Kon geen versie vinden voor {rwc_naam}")
    versie = max(int(v) for v in versies)
    return f"{JSON_REPO}/{rwc_naam}/{versie}/json/{rwc_naam}_{versie}.json"


def _value(node: dict[str, Any], predicate: str) -> str | None:
    """Pak de @value uit een JSON-LD-style predicate-array."""
    items = node.get(predicate)
    if not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    return unescape_html(first.get("@value"))


def _id(node: dict[str, Any], predicate: str) -> str | None:
    """Pak de @id uit een JSON-LD-style predicate-array."""
    items = node.get(predicate)
    if not items:
        return None
    first = items[0]
    return first.get("@id") if isinstance(first, dict) else None


def _is_huidige_versie(node: dict[str, Any]) -> bool:
    """Filter historische versies (HistorischeVersie-type) eruit."""
    types = node.get("@type") or []
    return all(not t.endswith("HistorischeVersie") for t in types) and not (
        _value(node, "https://identifier.overheid.nl/tooi/def/ont/einddatumHV")
    )


def _parse_rwc(
    rwc_naam: str,
    rwc_default_type: str,
    rwc_default_parent_synth: str | None,
    payload: list[dict[str, Any]],
) -> list[TooiOrganisatie]:
    out: list[TooiOrganisatie] = []
    for node in payload:
        if not _is_huidige_versie(node):
            continue
        tooi_uri = node.get("@id")
        if not tooi_uri or not tooi_uri.startswith(
            "https://identifier.overheid.nl/tooi/id/"
        ):
            continue
        # Skip event/metadata-types (Oprichting, Opheffing, Toestandswijziging,
        # Samenvoeging, Uitbreiding, RegisterwaardelijstCompleet, Ontology, Rijk-root).
        types = node.get("@type") or []
        skip_suffixes = (
            "Oprichting",
            "Opheffing",
            "Toestandswijziging",
            "Samenvoeging",
            "Uitbreiding",
            "RegisterwaardelijstCompleet",
            "owl#Ontology",
        )
        if any(t.endswith(skip_suffixes) for t in types):
            continue
        # 'Rijk' is een synthetische root-node binnen rwc_overige; skip
        if any(t.endswith("/Rijk") for t in types):
            continue
        naam = (
            _value(
                node,
                "https://identifier.overheid.nl/tooi/def/ont/voorkeursnaamInclSoort",
            )
            or _value(
                node,
                "https://identifier.overheid.nl/tooi/def/ont/officieleNaamInclSoort",
            )
            or _value(node, "http://www.w3.org/2000/01/rdf-schema#label")
        )
        if not naam or not naam.strip():
            continue
        einddatum_str = _value(
            node, "https://identifier.overheid.nl/tooi/def/ont/einddatum"
        )
        einddatum: date | None = None
        if einddatum_str:
            try:
                einddatum = datetime.fromisoformat(einddatum_str).date()
            except ValueError:
                einddatum = None
        out.append(
            TooiOrganisatie(
                tooi_uri=tooi_uri,
                naam=naam,
                afkorting=_value(
                    node, "https://identifier.overheid.nl/tooi/def/ont/afkorting"
                ),
                organisatiecode=_value(
                    node,
                    "https://identifier.overheid.nl/tooi/def/ont/organisatiecode",
                ),
                organisatiesoort=_id(
                    node,
                    "https://identifier.overheid.nl/tooi/def/ont/organisatiesoort",
                ),
                einddatum=einddatum,
                rwc_lijst=rwc_naam,
                rwc_default_type=rwc_default_type,
                rwc_default_parent_synth=rwc_default_parent_synth,
            )
        )
    return out


async def fetch_all() -> list[TooiOrganisatie]:
    """Haal alle 8 rwc-lijsten op en parse ze."""
    organisaties: list[TooiOrganisatie] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for rwc_naam, default_type, default_parent in RWC_LIJSTEN:
            url = await _resolve_latest_json_url(client, rwc_naam)
            log.info("fetching TOOI %s -> %s", rwc_naam, url)
            resp = await client.get(url)
            resp.raise_for_status()
            organisaties.extend(
                _parse_rwc(rwc_naam, default_type, default_parent, resp.json())
            )
    return organisaties


# --- Type/parent resolutie ---


def _resolveer_type_en_parent(
    org: TooiOrganisatie,
) -> tuple[str, str | None]:
    """Bepaal (type, synthetische_parent_naam) voor een TOOI-organisatie."""
    naam_lower = org.naam.lower()

    if org.rwc_lijst == "rwc_overige_overheidsorganisaties_compleet":
        if any(f in naam_lower for f in HCVS_FRAGMENTEN):
            return ("hoge_college_van_staat", "Hoge Colleges van Staat")
        if any(f in naam_lower for f in RECHTSPRAAK_FRAGMENTEN):
            return ("rechtspraak", "Rechtspraak")
        if any(f in naam_lower for f in OM_FRAGMENTEN):
            return ("openbaar_ministerie", "Openbaar Ministerie")
    return (org.rwc_default_type, org.rwc_default_parent_synth)


# --- Database upsert ---


def _normalize_name(naam: str) -> str:
    """Lower + collapse whitespace + strip type-prefixen.

    TOOI en organogram-scrape gebruiken vaak prefixen (`ministerie van`,
    `DG `, `agentschap `, `zbo `, `directoraat-generaal`) die handmatige
    rijen niet hebben. Voor conflict-detectie strippen we die zodat
    'Digitalisering en Overheidsorganisatie' matcht met
    'DG Digitalisering en Overheidsorganisatie'.

    Aanvullend: koppel-tekens en extra spaties opruimen, en een afkorting-
    suffix tussen haakjes verwijderen ('Rijksvastgoedbedrijf (RVB)' ->
    'Rijksvastgoedbedrijf').
    """
    n = " ".join(naam.lower().split())
    # Verwijder afkorting-suffix: 'naam (AFK)' -> 'naam'
    if n.endswith(")") and "(" in n:
        bracket = n.rfind("(")
        if bracket > 0:
            n = n[:bracket].strip()
    # Strip type-prefixen
    prefixen = (
        "ministerie van ",
        "directoraat-generaal ",
        "directoraat generaal ",
        "dg ",
        "agentschap ",
        "zbo ",
        "stichting ",
    )
    veranderd = True
    while veranderd:
        veranderd = False
        for p in prefixen:
            if n.startswith(p):
                n = n[len(p) :]
                veranderd = True
                break
    return n.strip()


async def _synthetische_parent_map(
    session: AsyncSession,
) -> dict[str, uuid.UUID]:
    """Lees de synthetische groepen uit de DB."""
    rows = (
        await session.execute(
            select(OrganisatieEenheid.id, OrganisatieEenheid.naam).where(
                OrganisatieEenheid.bron == "synthetisch"
            )
        )
    ).all()
    return {naam: id_ for (id_, naam) in rows}


async def _has_actieve_plaatsing(session: AsyncSession, eenheid_id) -> bool:
    """True als er minstens één lopende plaatsing aan deze eenheid hangt."""
    from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

    result = await session.execute(
        select(PersonOrganisatieEenheid.id)
        .where(
            PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid_id,
            PersonOrganisatieEenheid.eind_datum.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _existing_by_tooi_uri(
    session: AsyncSession,
) -> dict[str, OrganisatieEenheid]:
    rows = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.tooi_uri.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.tooi_uri: row for row in rows if row.tooi_uri}


async def _existing_manual_by_name(
    session: AsyncSession,
) -> dict[str, OrganisatieEenheid]:
    """Map van genormaliseerde naam -> handmatige rij (voor conflict-detectie)."""
    rows = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.bron == "handmatig",
                    OrganisatieEenheid.tooi_uri.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, OrganisatieEenheid] = {}
    for r in rows:
        out[_normalize_name(r.naam)] = r
        if r.afkorting:
            out[r.afkorting.lower()] = r
    return out


async def _existing_synthetic_by_name(
    session: AsyncSession,
) -> dict[str, OrganisatieEenheid]:
    rows = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.bron == "synthetisch"
                )
            )
        )
        .scalars()
        .all()
    )
    return {r.naam: r for r in rows}


@dataclass
class SyncStats:
    sync_run_id: uuid.UUID
    added: int = 0
    renamed: int = 0
    moved: int = 0
    soft_deleted: int = 0
    enriched: int = 0
    conflicts: int = 0
    skipped_sanity: bool = False


async def sync_tooi(
    session: AsyncSession,
    *,
    fetcher=fetch_all,
    sanity_max_soft_delete_pct: float = 0.05,
    commit: bool = True,
) -> SyncStats:
    """Voer een TOOI-sync uit. Geeft statistieken terug.

    Met commit=False (voor tests in een rolled-back transaction) doet de
    sync een `flush()` aan het eind in plaats van `commit()`. De caller is
    dan verantwoordelijk voor commit/rollback.
    """
    sync_run_id = uuid.uuid4()
    stats = SyncStats(sync_run_id=sync_run_id)

    feed = await fetcher()
    if not feed:
        log.error("TOOI feed leeg, sync afgebroken")
        stats.skipped_sanity = True
        from bouwmeester.services.sync_notifications import notify_super_admins

        await notify_super_admins(
            session,
            title="TOOI-sync overgeslagen",
            message=(
                "TOOI-feed leverde 0 organisaties. Sync is afgebroken. "
                "Check standaarden.overheid.nl/tooi/waardelijsten."
            ),
        )
        if commit:
            await session.commit()
        else:
            await session.flush()
        return stats

    bestaand = await _existing_by_tooi_uri(session)
    handmatig_per_naam = await _existing_manual_by_name(session)
    synth_per_naam = await _existing_synthetic_by_name(session)

    # Sanity-check op massale soft-delete: hoeveel uri's zouden verdwijnen?
    feed_uris = {o.tooi_uri for o in feed}
    bestaande_actief = [e for e in bestaand.values() if e.geldig_tot is None]
    zou_verdwijnen = [e for e in bestaande_actief if e.tooi_uri not in feed_uris]
    if (
        bestaande_actief
        and len(zou_verdwijnen) / len(bestaande_actief) > sanity_max_soft_delete_pct
    ):
        log.error(
            "TOOI sanity-check: %d/%d (%.1f%%) zouden soft-deleted worden, abort",
            len(zou_verdwijnen),
            len(bestaande_actief),
            100.0 * len(zou_verdwijnen) / len(bestaande_actief),
        )
        stats.skipped_sanity = True
        session.add(
            TooiSyncLog(
                sync_run_id=sync_run_id,
                bron="tooi",
                action="conflict",
                note=(
                    f"Sanity check abort: {len(zou_verdwijnen)}/"
                    f"{len(bestaande_actief)} zouden soft-deleted worden"
                ),
            )
        )
        from bouwmeester.services.sync_notifications import notify_super_admins

        await notify_super_admins(
            session,
            title="TOOI-sync sanity-check geblokkeerd",
            message=(
                f"De TOOI-feed zou {len(zou_verdwijnen)} van "
                f"{len(bestaande_actief)} actieve organisaties soft-deleten "
                f"({100.0 * len(zou_verdwijnen) / len(bestaande_actief):.1f}%) — "
                "boven de drempel van "
                f"{sanity_max_soft_delete_pct * 100:.0f}%. Sync afgebroken."
            ),
        )
        if commit:
            await session.commit()
        else:
            await session.flush()
        return stats

    today = date.today()

    # Upsert per feed-rij
    for org in feed:
        type_, parent_synth = _resolveer_type_en_parent(org)
        parent_id: uuid.UUID | None = None
        if parent_synth and parent_synth in synth_per_naam:
            parent_id = synth_per_naam[parent_synth].id

        if org.tooi_uri in bestaand:
            # bestaande TOOI-rij: update velden
            row = bestaand[org.tooi_uri]
            before = {
                "naam": row.naam,
                "type": row.type,
                "parent_id": str(row.parent_id) if row.parent_id else None,
                "afkorting": row.afkorting,
            }
            naam_changed = row.naam != org.naam
            type_changed = row.type != type_
            parent_changed = (parent_id is not None and row.parent_id != parent_id) or (
                parent_id is None and row.parent_id is None and False
            )

            row.naam = org.naam
            row.type = type_
            if row.afkorting != org.afkorting:
                row.afkorting = org.afkorting
            if parent_id is not None and row.parent_id != parent_id:
                row.parent_id = parent_id
            if row.tooi_organisatiesoort != org.organisatiesoort:
                row.tooi_organisatiesoort = org.organisatiesoort
            # Einddatum-merge regels:
            # - TOOI markeert als opgeheven EN onze rij was actief: alleen
            #   overnemen als er GEEN actieve plaatsing aan hangt (anders
            #   respecteren we de heractivering door kabinet-scrape).
            # - TOOI markeert weer als levend: clear geldig_tot.
            if org.einddatum is not None:
                if row.geldig_tot is None:
                    has_active = await _has_actieve_plaatsing(session, row.id)
                    if has_active and org.einddatum < today:
                        # Skip soft-delete; ministerie is in gebruik (bv.
                        # kabinet-scrape heeft hem geheractiveerd na een
                        # eerdere TOOI-soft-delete).
                        log.info(
                            "TOOI markeert %s als opgeheven %s, maar er "
                            "zijn actieve plaatsingen — geheractiveerd",
                            row.naam,
                            org.einddatum,
                        )
                    else:
                        row.geldig_tot = org.einddatum
                elif row.geldig_tot != org.einddatum:
                    row.geldig_tot = org.einddatum
            elif row.geldig_tot is not None:
                # TOOI ziet hem nu als levend, was eerder soft-deleted
                row.geldig_tot = None

            if naam_changed:
                stats.renamed += 1
            if parent_changed:
                stats.moved += 1
            if naam_changed or type_changed or parent_changed:
                session.add(
                    TooiSyncLog(
                        sync_run_id=sync_run_id,
                        bron="tooi",
                        action="rename" if naam_changed else "move",
                        tooi_uri=org.tooi_uri,
                        organisatie_eenheid_id=row.id,
                        before=before,
                        after={
                            "naam": org.naam,
                            "type": type_,
                            "parent_id": (str(parent_id) if parent_id else None),
                            "afkorting": org.afkorting,
                        },
                    )
                )
            continue

        # Nieuwe rij: check eerst conflict met handmatige
        norm_naam = _normalize_name(org.naam)
        kandidaat = handmatig_per_naam.get(norm_naam)
        if (
            kandidaat is None
            and org.afkorting
            and org.afkorting.lower() in handmatig_per_naam
        ):
            kandidaat = handmatig_per_naam[org.afkorting.lower()]

        nieuw = OrganisatieEenheid(
            naam=org.naam,
            type=type_,
            parent_id=parent_id,
            afkorting=org.afkorting,
            tooi_uri=org.tooi_uri,
            tooi_organisatiesoort=org.organisatiesoort,
            bron="tooi",
            geldig_van=today,
            geldig_tot=org.einddatum,
        )
        session.add(nieuw)
        stats.added += 1
        await session.flush()

        if kandidaat is not None:
            session.add(
                PendingReconciliation(
                    resource_type="organisatie_eenheid",
                    handmatige_id=kandidaat.id,
                    kandidaat_id=nieuw.id,
                    kandidaat_bron="tooi",
                    match_reden=(
                        "afkorting"
                        if (
                            org.afkorting
                            and org.afkorting.lower() in handmatig_per_naam
                            and handmatig_per_naam[org.afkorting.lower()].id
                            == kandidaat.id
                        )
                        else "naam_normalized"
                    ),
                    details={
                        "tooi_naam": org.naam,
                        "tooi_uri": org.tooi_uri,
                        "tooi_afkorting": org.afkorting,
                        "handmatige_naam": kandidaat.naam,
                        "handmatige_afkorting": kandidaat.afkorting,
                    },
                )
            )
            stats.conflicts += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="tooi",
                    action="conflict",
                    tooi_uri=org.tooi_uri,
                    organisatie_eenheid_id=nieuw.id,
                    note=(
                        f"Naam-conflict met handmatige rij {kandidaat.id} "
                        f"({kandidaat.naam})"
                    ),
                )
            )
        else:
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="tooi",
                    action="add",
                    tooi_uri=org.tooi_uri,
                    organisatie_eenheid_id=nieuw.id,
                    after={
                        "naam": org.naam,
                        "type": type_,
                        "afkorting": org.afkorting,
                    },
                )
            )

    # Soft-delete: TOOI-rijen die niet meer in feed zitten
    for row in zou_verdwijnen:
        row.geldig_tot = today
        stats.soft_deleted += 1
        session.add(
            TooiSyncLog(
                sync_run_id=sync_run_id,
                bron="tooi",
                action="soft_delete",
                tooi_uri=row.tooi_uri,
                organisatie_eenheid_id=row.id,
                note="afwezig in TOOI feed",
            )
        )

    # Eén batch-notificatie als er conflicts zijn die handmatige review nodig
    # hebben — niet per conflict, anders krijgen super_admins 100en mails.
    if stats.conflicts > 0:
        from bouwmeester.services.sync_notifications import notify_super_admins

        await notify_super_admins(
            session,
            title=f"TOOI-sync: {stats.conflicts} reconciliation(s) open",
            message=(
                f"De laatste TOOI-sync heeft {stats.conflicts} naam-conflict(en) "
                "gedetecteerd tussen handmatige rijen en TOOI-data. "
                "Open ze in Beheer > Reconciliatie om te mergen of te negeren."
            ),
        )

    if commit:
        await session.commit()
    else:
        await session.flush()
    log.info(
        "TOOI sync run=%s: +%d added, %d renamed, %d moved, "
        "%d soft_deleted, %d conflicts",
        sync_run_id,
        stats.added,
        stats.renamed,
        stats.moved,
        stats.soft_deleted,
        stats.conflicts,
    )

    # Auto-merge ministeries: één-op-één naam-match tussen handmatige
    # ministerie-rij en TOOI-rij is veilig (ministerie-namen zijn wettelijk
    # uniek). Idempotent: bij volgende runs zijn er geen open conflicten meer
    # voor type=ministerie en doet de helper niks.
    if stats.conflicts > 0 and commit:
        from bouwmeester.services.auto_merge_ministries import merge_ministries

        n_merged = await merge_ministries(session)
        if n_merged:
            log.info("Auto-merge ministeries: %d rijen samengevoegd", n_merged)

    return stats
