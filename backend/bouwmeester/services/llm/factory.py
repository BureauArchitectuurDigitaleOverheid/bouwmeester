"""Factory for LLM service instances with capability-based routing.

Settings are read from:
1. AppConfig table in the database (set via admin panel)
2. Environment variables / config.py settings (fallback)

Service instances and config are cached in memory. The cache is cleared
when an admin updates config via the admin panel.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.services.llm.base import BaseLLMService, DataSensitivity

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

    # Build VLAM
    vlam_key = config.get("VLAM_API_KEY") or settings.VLAM_API_KEY
    vlam_url = config.get("VLAM_BASE_URL") or settings.VLAM_BASE_URL
    vlam_model = config.get("VLAM_MODEL_ID") or settings.VLAM_MODEL_ID
    if vlam_key and vlam_url:
        from bouwmeester.services.llm.vlam_service import VlamLLMService

        _vlam_cache = VlamLLMService(
            api_key=vlam_key, base_url=vlam_url, model=vlam_model
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
