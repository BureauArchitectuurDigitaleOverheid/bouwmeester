"""Factory for LLM service instances with capability-based routing.

Settings are read from:
1. AppConfig table in the database (set via admin panel)
2. Environment variables / config.py settings (fallback)

All public functions are async because they read from the database.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.services.llm.base import BaseLLMService, DataSensitivity

logger = logging.getLogger(__name__)

# In-memory cache — cleared by admin config update endpoint.
_config_cache: dict[str, str] | None = None


def clear_config_cache() -> None:
    """Clear the cached config so the next request reads fresh values."""
    global _config_cache  # noqa: PLW0603
    _config_cache = None


async def _load_config(db: AsyncSession) -> dict[str, str]:
    """Load LLM config from the AppConfig table."""
    global _config_cache  # noqa: PLW0603
    if _config_cache is not None:
        return _config_cache

    try:
        from bouwmeester.models.app_config import AppConfig

        result = await db.execute(select(AppConfig.key, AppConfig.value))
        _config_cache = {row[0]: row[1] for row in result.all() if row[1]}
    except Exception:
        logger.debug("Could not load config from database, using env vars")
        _config_cache = {}

    return _config_cache


def _build_claude(config: dict[str, str]) -> BaseLLMService | None:
    settings = get_settings()
    api_key = config.get("ANTHROPIC_API_KEY") or settings.ANTHROPIC_API_KEY
    model = config.get("LLM_MODEL") or settings.LLM_MODEL
    if not api_key:
        return None
    from bouwmeester.services.llm.claude_service import ClaudeLLMService

    return ClaudeLLMService(api_key=api_key, model=model)


def _build_vlam(config: dict[str, str]) -> BaseLLMService | None:
    settings = get_settings()
    api_key = config.get("VLAM_API_KEY") or settings.VLAM_API_KEY
    base_url = config.get("VLAM_BASE_URL") or settings.VLAM_BASE_URL
    model = config.get("VLAM_MODEL_ID") or settings.VLAM_MODEL_ID
    if not api_key or not base_url:
        return None
    from bouwmeester.services.llm.vlam_service import VlamLLMService

    return VlamLLMService(api_key=api_key, base_url=base_url, model=model)


async def get_llm_service(
    db: AsyncSession,
) -> BaseLLMService | None:
    """Return the default LLM service (any provider, for public data).

    Uses LLM_PROVIDER setting to pick the preferred provider.
    Falls back to the other provider if the preferred one is unavailable.
    """
    config = await _load_config(db)
    settings = get_settings()
    preferred = config.get("LLM_PROVIDER") or settings.LLM_PROVIDER

    if preferred == "vlam":
        return _build_vlam(config) or _build_claude(config)

    return _build_claude(config) or _build_vlam(config)


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

    config = await _load_config(db)
    settings = get_settings()
    preferred = config.get("LLM_PROVIDER") or settings.LLM_PROVIDER

    if preferred == "vlam":
        candidates = [_build_vlam(config), _build_claude(config)]
    else:
        candidates = [_build_claude(config), _build_vlam(config)]

    for service in candidates:
        if service and service.capabilities.supports(sensitivity):
            return service

    return None
