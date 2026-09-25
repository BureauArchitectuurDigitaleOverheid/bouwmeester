"""Factory for LLM service instances with capability-based routing.

Settings are read from:
1. AppConfig table in the database (set via admin panel)
2. Environment variables / config.py settings (fallback)

Service instances and config are cached in memory. De cache wordt geleegd
wanneer een beheerder de configuratie aanpast, en verloopt daarnaast vanzelf
na ``_CONFIG_CACHE_TTL_SECONDS``.

Die TTL is nodig omdat de caches PER PROCES zijn. De achtergrondworker draait
apart van de webserver (zie ``entrypoint.sh``), dus een wijziging via het
beheerscherm leegt alleen de cache van de webserver. Juist de worker doet het
LLM-werk — lead-classificatie op Mattermost-berichten — dus zonder TTL bleef
een gecorrigeerd model of een nieuwe sleutel daar onzichtbaar tot een
herstart, terwijl het beheerscherm de wijziging netjes opgeslagen toonde.
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.services.llm.base import BaseLLMService, DataSensitivity
from bouwmeester.services.llm.vlam_endpoint import resolve_vlam_base_url

logger = logging.getLogger(__name__)

# In-memory caches — cleared by admin config update endpoint, en daarnaast
# na _CONFIG_CACHE_TTL vanzelf verlopen.
#
# Die TTL is er omdat de worker een ANDER proces is dan de webserver
# (entrypoint.sh start `python -m bouwmeester.worker` apart). Een beheerder
# die in Beheer > Instellingen een LLM-sleutel of model wijzigt, raakt
# alleen de cache van de webserver; de worker bleef het oude model gebruiken
# tot een herstart. Dat is stil en verwarrend: de wijziging staat opgeslagen
# en er verandert niets aan de lead-classificatie, die juist in de worker
# draait. Zelfde patroon als _load_mattermost_config.
_CONFIG_CACHE_TTL_SECONDS = 60

_config_cache: dict[str, str] | None = None
_config_cache_ts: float = 0.0
_claude_cache: BaseLLMService | None = None
_vlam_cache: BaseLLMService | None = None
_services_built = False


def clear_config_cache() -> None:
    """Clear all caches so the next request rebuilds from the database."""
    global _config_cache, _claude_cache, _vlam_cache, _services_built  # noqa: PLW0603
    global _config_cache_ts  # noqa: PLW0603
    global _last_logged_summary  # noqa: PLW0603
    _config_cache = None
    _config_cache_ts = 0.0
    _claude_cache = None
    _vlam_cache = None
    _services_built = False
    _last_logged_summary = None


def _config_cache_expired() -> bool:
    """True als de gecachte configuratie ouder is dan de TTL."""
    return (time.monotonic() - _config_cache_ts) >= _CONFIG_CACHE_TTL_SECONDS


async def _load_config(db: AsyncSession) -> dict[str, str]:
    """Load LLM config from the AppConfig table, decrypting secrets."""
    global _config_cache, _config_cache_ts  # noqa: PLW0603
    if _config_cache is not None and not _config_cache_expired():
        return _config_cache

    try:
        from bouwmeester.core.encryption import decrypt_value
        from bouwmeester.models.app_config import AppConfig

        result = await db.execute(
            select(AppConfig.key, AppConfig.value, AppConfig.is_secret)
        )
        _config_cache = {}
        for key, value, is_secret in result.all():
            if value:
                _config_cache[key] = decrypt_value(value) if is_secret else value
        _config_cache_ts = time.monotonic()
    except Exception:
        logger.debug("Could not load config from database, using env vars")
        # Niet cachen bij een DB-fout: anders zit je een hele TTL lang aan
        # een lege configuratie vast terwijl de database alweer terug is.
        return {}

    return _config_cache


#: Laatst gelogde configuratie-samenvatting. Sinds de TTL-herbouw draait
#: _ensure_services elke minuut opnieuw; zonder deze rem zou dat elke minuut
#: dezelfde regel in de log zetten.
_last_logged_summary: tuple | None = None


def _log_llm_configuration(
    *,
    claude_built: bool,
    claude_model: str,
    # Welke route Claude gebruikt: "cli (abonnement)" of "api-sleutel".
    # Optioneel, zodat aanroepers die alleen willen weten óf er een
    # provider is (en de tests die dat controleren) niets hoeven te weten
    # van de betaalroute.
    claude_via: str = "",
    vlam_built: bool,
    vlam_key: str,
    vlam_url: str,
    vlam_model: str,
    platform_url: str,
    manual_url: str,
    preferred: str,
) -> None:
    """Log één keer per proces welke LLM-providers er zijn opgebouwd.

    Zonder dit is "de taalmodel-dienst is niet bereikbaar" niet te
    onderscheiden van "er is helemaal geen provider geconfigureerd": het
    eerste doet een netwerkcall die faalt, het tweede doet er geen. Dat
    verschil kostte een middag uitzoeken, en het is van buitenaf niet te
    zien omdat de configuratie in de pod-omgeving zit.

    Adressen zijn geen geheim (een intern cluster-adres zegt niets dat de
    beheerder niet mag weten), de sleutel uiteraard wel: daarvan loggen we
    alleen of hij gezet is.
    """
    global _last_logged_summary  # noqa: PLW0603
    summary = (
        claude_built,
        claude_via,
        claude_model,
        vlam_built,
        vlam_url,
        vlam_model,
        bool(vlam_key),
        preferred,
    )
    if summary == _last_logged_summary:
        return
    _last_logged_summary = summary

    logger.info(
        "LLM-providers: claude=%s (model=%s, via=%s), vlam=%s, voorkeur=%s",
        "ja" if claude_built else "nee",
        claude_model or "-",
        claude_via or "-",
        "ja" if vlam_built else "nee",
        preferred or "-",
    )

    # Wie het publieke werk krijgt, met de reden erbij. De regel hierboven
    # geeft de ingrediënten; deze geeft de uitkomst, en dat is wat je wil
    # weten als je net `LLM_PROVIDER` hebt omgezet. Zonder deze regel is
    # het antwoord alleen af te leiden uit een traceback van een mislukte
    # aanroep, en dat was op 25 september 2026 precies het probleem.
    if preferred == "vlam":
        winnaar, reden = (
            ("VLAM", "voorkeur") if vlam_built else ("Claude", "VLAM niet opgebouwd")
        )
    else:
        winnaar, reden = (
            ("Claude", "voorkeur")
            if claude_built
            else ("VLAM", "Claude niet opgebouwd")
        )
    if not (claude_built or vlam_built):
        winnaar, reden = ("geen", "geen enkele provider opgebouwd")

    logger.info(
        "Publiek werk (kamerstukken, samenvattingen) gaat naar: %s (%s). "
        "Intern en vertrouwelijk werk gaat altijd naar VLAM, ongeacht de "
        "voorkeur: Claude draagt alleen PUBLIC.",
        winnaar,
        reden,
    )
    if vlam_built:
        bron = (
            "platform (VLAM_API_URL)" if platform_url else "handmatig (VLAM_BASE_URL)"
        )
        logger.info(
            "VLAM actief: base_url=%s (bron: %s), model=%s",
            vlam_url,
            bron,
            vlam_model or "-",
        )
        return

    # Niet opgebouwd: benoem welke ingrediënt ontbreekt. CONFIDENTIAL-werk
    # (lead-classificatie) kan alleen via VLAM, dus dit is geen detail.
    ontbreekt = []
    if not vlam_key:
        ontbreekt.append("VLAM_API_KEY")
    if not vlam_url:
        if platform_url or manual_url:
            ontbreekt.append(
                f"bruikbare URL (VLAM_API_URL={platform_url or '-'!r}, "
                f"VLAM_BASE_URL={manual_url or '-'!r})"
            )
        else:
            ontbreekt.append("VLAM_API_URL of VLAM_BASE_URL (beide leeg)")
    logger.warning(
        "VLAM niet opgebouwd — ontbreekt: %s. Lead-classificatie en ander "
        "CONFIDENTIAL-werk blijven uit tot dit gezet is.",
        ", ".join(ontbreekt),
    )


async def _ensure_services(db: AsyncSession) -> None:
    """Build and cache service instances if not already built.

    Bouwt ook opnieuw op zodra de configuratie-cache verlopen is. Alleen de
    config verversen is niet genoeg: de clients dragen sleutel, adres en
    model in zich, dus zonder herbouw blijft een gewijzigd model in een
    ander proces onzichtbaar.
    """
    global _claude_cache, _vlam_cache, _services_built  # noqa: PLW0603
    if _services_built and not _config_cache_expired():
        return

    _claude_cache = None
    _vlam_cache = None

    config = await _load_config(db)
    settings = get_settings()

    # Build Claude. Het abonnementstoken gaat vóór op de API-sleutel: die
    # laatste rekent per token af, het eerste loopt op een abonnement. Ze
    # spreken hetzelfde model aan, dus als beide gezet zijn is de
    # goedkoopste route de juiste.
    api_key = config.get("ANTHROPIC_API_KEY") or settings.ANTHROPIC_API_KEY
    model = config.get("LLM_MODEL") or settings.LLM_MODEL
    oauth_token = (
        config.get("CLAUDE_CODE_OAUTH_TOKEN") or settings.CLAUDE_CODE_OAUTH_TOKEN
    )
    claude_via = ""
    if oauth_token:
        from bouwmeester.services.llm.claude_cli_service import (
            ClaudeCliLLMService,
            cli_available,
        )

        # Zonder binary geen provider: hem toch opbouwen zou elke call laten
        # falen op een FileNotFoundError, terwijl terugvallen op de
        # API-sleutel of VLAM precies is wat je dan wilt.
        if cli_available():
            _claude_cache = ClaudeCliLLMService(model=model, oauth_token=oauth_token)
            claude_via = "cli (abonnement)"
        else:
            logger.warning(
                "CLAUDE_CODE_OAUTH_TOKEN is gezet maar de `claude`-binary "
                "ontbreekt in deze image; val terug op de API-sleutel"
            )
    if _claude_cache is None and api_key:
        from bouwmeester.services.llm.claude_service import ClaudeLLMService

        _claude_cache = ClaudeLLMService(api_key=api_key, model=model)
        claude_via = "api-sleutel"

    # Build VLAM. Het platform-adres (ZAD-dienst `vlam`) gaat vóór op een
    # handmatig ingestelde URL; zie resolve_vlam_base_url.
    vlam_key = config.get("VLAM_API_KEY") or settings.VLAM_API_KEY
    platform_url = config.get("VLAM_API_URL") or settings.VLAM_API_URL
    manual_url = config.get("VLAM_BASE_URL") or settings.VLAM_BASE_URL
    vlam_url = resolve_vlam_base_url(platform_url, manual_url)
    vlam_model = config.get("VLAM_MODEL_ID") or settings.VLAM_MODEL_ID
    if vlam_key and vlam_url:
        from bouwmeester.services.llm.vlam_service import VlamLLMService

        _vlam_cache = VlamLLMService(
            api_key=vlam_key, base_url=vlam_url, model=vlam_model
        )

    _log_llm_configuration(
        claude_built=_claude_cache is not None,
        claude_via=claude_via,
        claude_model=model,
        vlam_built=_vlam_cache is not None,
        vlam_key=vlam_key,
        vlam_url=vlam_url,
        vlam_model=vlam_model,
        platform_url=platform_url,
        manual_url=manual_url,
        preferred=config.get("LLM_PROVIDER") or settings.LLM_PROVIDER,
    )

    _services_built = True


async def get_llm_service(
    db: AsyncSession,
) -> BaseLLMService | None:
    """Return the default LLM service (any provider, for public data).

    Uses LLM_PROVIDER setting to pick the preferred provider.
    Falls back to the other provider if the preferred one is unavailable.
    """
    await _ensure_services(db)
    config = await _load_config(db)
    settings = get_settings()
    preferred = config.get("LLM_PROVIDER") or settings.LLM_PROVIDER

    if preferred == "vlam":
        return _vlam_cache or _claude_cache

    return _claude_cache or _vlam_cache


async def get_llm_service_for(
    sensitivity: DataSensitivity,
    db: AsyncSession,
) -> BaseLLMService | None:
    """Return an LLM service that supports the given data sensitivity.

    For PUBLIC data: any configured provider.
    For INTERNAL/CONFIDENTIAL: only providers that declare support.
    Returns None if no suitable provider is configured.
    """
    if sensitivity == DataSensitivity.PUBLIC:
        return await get_llm_service(db)

    await _ensure_services(db)
    config = await _load_config(db)
    settings = get_settings()
    preferred = config.get("LLM_PROVIDER") or settings.LLM_PROVIDER

    if preferred == "vlam":
        candidates = [_vlam_cache, _claude_cache]
    else:
        candidates = [_claude_cache, _vlam_cache]

    for service in candidates:
        if service and service.capabilities.supports(sensitivity):
            return service

    return None
