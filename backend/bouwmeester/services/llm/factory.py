"""Factory for LLM service instances with capability-based routing.

Settings are read from:
1. AppConfig table in the database (set via admin panel)
2. Environment variables / config.py settings (fallback)

Service instances and config are cached in memory. The cache is cleared
when an admin updates config via the admin panel.

NOTE: Caches are per-process. In a multi-worker deployment, only the worker
that handles the admin config update will have its cache cleared immediately.
Other workers will continue using stale config until they are restarted or
recycled. This is acceptable for admin-initiated config changes (infrequent)
but should be revisited if real-time propagation is needed (e.g. via Redis pub/sub).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.services.llm.base import BaseLLMService, DataSensitivity
from bouwmeester.services.llm.vlam_endpoint import resolve_vlam_base_url

logger = logging.getLogger(__name__)

# In-memory caches — cleared by admin config update endpoint.
_config_cache: dict[str, str] | None = None
_claude_cache: BaseLLMService | None = None
_vlam_cache: BaseLLMService | None = None
_services_built = False


def clear_config_cache() -> None:
    """Clear all caches so the next request rebuilds from the database."""
    global _config_cache, _claude_cache, _vlam_cache, _services_built  # noqa: PLW0603
    _config_cache = None
    _claude_cache = None
    _vlam_cache = None
    _services_built = False


async def _load_config(db: AsyncSession) -> dict[str, str]:
    """Load LLM config from the AppConfig table, decrypting secrets."""
    global _config_cache  # noqa: PLW0603
    if _config_cache is not None:
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
    except Exception:
        logger.debug("Could not load config from database, using env vars")
        _config_cache = {}

    return _config_cache


def _log_llm_configuration(
    *,
    claude_built: bool,
    claude_model: str,
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
    logger.info(
        "LLM-providers: claude=%s (model=%s), vlam=%s, voorkeur=%s",
        "ja" if claude_built else "nee",
        claude_model or "-",
        "ja" if vlam_built else "nee",
        preferred or "-",
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
    """Build and cache service instances if not already built."""
    global _claude_cache, _vlam_cache, _services_built  # noqa: PLW0603
    if _services_built:
        return

    config = await _load_config(db)
    settings = get_settings()

    # Build Claude
    api_key = config.get("ANTHROPIC_API_KEY") or settings.ANTHROPIC_API_KEY
    model = config.get("LLM_MODEL") or settings.LLM_MODEL
    if api_key:
        from bouwmeester.services.llm.claude_service import ClaudeLLMService

        _claude_cache = ClaudeLLMService(api_key=api_key, model=model)

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
