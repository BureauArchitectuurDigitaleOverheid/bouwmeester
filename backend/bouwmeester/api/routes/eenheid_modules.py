"""API routes for eenheid module toggles."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.repositories.eenheid_module import EenheidModuleRepository
from bouwmeester.schema.eenheid_module import (
    MODULE_LABELS,
    VALID_MODULES,
    EenheidModuleResponse,
    EenheidModulesResponse,
    EenheidModuleUpdate,
)
from bouwmeester.services.activity_service import log_activity

router = APIRouter(prefix="/eenheid-modules", tags=["eenheid-modules"])


@router.get(
    "/{eenheid_id}",
    response_model=EenheidModulesResponse,
)
async def get_eenheid_modules(
    eenheid_id: UUID,
    _perm=Depends(require_permission("org:manage")),
    db: AsyncSession = Depends(get_db),
) -> EenheidModulesResponse:
    """Get module config for an eenheid, including inherited state."""
    require_found(await db.get(OrganisatieEenheid, eenheid_id), "Eenheid")
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
    current_user: OptionalUser,
    _perm=Depends(require_permission("org:manage")),
    db: AsyncSession = Depends(get_db),
) -> EenheidModulesResponse:
    """Toggle a module on/off for an eenheid."""
    eenheid = require_found(await db.get(OrganisatieEenheid, eenheid_id), "Eenheid")

    repo = EenheidModuleRepository(db)

    if data.enabled:
        await repo.delete_module(eenheid_id, data.module)
    else:
        await repo.set_module(eenheid_id, data.module, enabled=False)

    await log_activity(
        db,
        current_user,
        None,
        "eenheid_module.updated",
        details={
            "eenheid_id": str(eenheid_id),
            "eenheid_naam": eenheid.naam,
            "module": data.module,
            "enabled": data.enabled,
        },
    )

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
    _perm=Depends(require_permission("org:manage")),
) -> dict[str, str]:
    """Return the list of toggleable modules with labels."""
    return {k: MODULE_LABELS[k] for k in sorted(VALID_MODULES)}
