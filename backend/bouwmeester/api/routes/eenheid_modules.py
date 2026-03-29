"""API routes for eenheid module toggles."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.repositories.eenheid_module import EenheidModuleRepository
from bouwmeester.schema.eenheid_module import (
    VALID_MODULES,
    EenheidModuleResponse,
    EenheidModulesResponse,
    EenheidModuleUpdate,
)

router = APIRouter(prefix="/eenheid-modules", tags=["eenheid-modules"])


@router.get(
    "/{eenheid_id}",
    response_model=EenheidModulesResponse,
)
async def get_eenheid_modules(
    eenheid_id: UUID,
    _perm=Depends(require_permission("feature_toggle:manage")),
    db: AsyncSession = Depends(get_db),
) -> EenheidModulesResponse:
    """Get module config for an eenheid, including inherited state."""
    repo = EenheidModuleRepository(db)
    configs = await repo.get_full_config(eenheid_id)
    return EenheidModulesResponse(
        eenheid_id=eenheid_id,
        modules=[EenheidModuleResponse(**c) for c in configs],
    )


@router.put(
    "/{eenheid_id}",
    response_model=EenheidModulesResponse,
)
async def update_eenheid_module(
    eenheid_id: UUID,
    data: EenheidModuleUpdate,
    _perm=Depends(require_permission("feature_toggle:manage")),
    db: AsyncSession = Depends(get_db),
) -> EenheidModulesResponse:
    """Toggle a module on/off for an eenheid."""
    repo = EenheidModuleRepository(db)

    if data.enabled:
        # Enabling = remove the override (revert to default)
        await repo.delete_module(eenheid_id, data.module)
    else:
        await repo.set_module(eenheid_id, data.module, enabled=False)

    configs = await repo.get_full_config(eenheid_id)
    return EenheidModulesResponse(
        eenheid_id=eenheid_id,
        modules=[EenheidModuleResponse(**c) for c in configs],
    )


@router.get(
    "",
    response_model=dict[str, str],
)
async def get_available_modules(
    _perm=Depends(require_permission("feature_toggle:manage")),
) -> dict[str, str]:
    """Return the list of toggleable modules with labels."""
    from bouwmeester.schema.eenheid_module import MODULE_LABELS

    return {k: MODULE_LABELS[k] for k in sorted(VALID_MODULES)}
