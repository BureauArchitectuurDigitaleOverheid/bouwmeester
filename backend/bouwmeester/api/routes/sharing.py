"""Cross-org shared access management routes."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.core.permissions import require_permission
from bouwmeester.repositories.shared_access import SharedAccessRepository
from bouwmeester.schema.shared_access import (
    SharedAccessCreate,
    SharedAccessResponse,
)

router = APIRouter(prefix="/sharing", tags=["sharing"])


def _to_response(sa) -> SharedAccessResponse:
    return SharedAccessResponse(
        id=sa.id,
        source_node_id=sa.source_node_id,
        source_eenheid_id=sa.source_eenheid_id,
        source_eenheid_naam=(sa.source_eenheid.naam if sa.source_eenheid else None),
        target_eenheid_id=sa.target_eenheid_id,
        target_eenheid_naam=(sa.target_eenheid.naam if sa.target_eenheid else None),
        access_level=sa.access_level,
        shared_by_id=sa.shared_by_id,
        reason=sa.reason,
        geldig_van=sa.geldig_van,
        geldig_tot=sa.geldig_tot,
        created_at=sa.created_at,
    )


@router.get("", response_model=list[SharedAccessResponse])
async def list_shares(
    _perm=Depends(require_permission("org:read")),
    org_ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
):
    """List active shares involving the user's eenheden."""
    repo = SharedAccessRepository(db)
    eenheid_ids = org_ctx.own_eenheid_ids
    if org_ctx.is_admin:
        # Admins see all — use empty list trick won't work,
        # so just return all
        from sqlalchemy import select

        from bouwmeester.models.shared_access import (
            SharedAccess,
        )

        stmt = select(SharedAccess).order_by(SharedAccess.created_at.desc())
        result = await db.execute(stmt)
        shares = list(result.scalars().all())
    else:
        shares = await repo.list_for_eenheden(eenheid_ids)
    return [_to_response(s) for s in shares]


@router.post("", response_model=SharedAccessResponse)
async def create_share(
    data: SharedAccessCreate,
    perm=Depends(require_permission("org:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a shared access grant."""
    from bouwmeester.models.shared_access import SharedAccess

    share = SharedAccess(
        source_node_id=data.source_node_id,
        source_eenheid_id=data.source_eenheid_id,
        target_eenheid_id=data.target_eenheid_id,
        access_level=data.access_level,
        shared_by_id=perm.person_id,
        reason=data.reason,
        geldig_van=data.geldig_van or date.today(),
        geldig_tot=data.geldig_tot,
    )
    db.add(share)
    await db.flush()
    await db.refresh(share)
    return SharedAccessResponse(
        id=share.id,
        source_node_id=share.source_node_id,
        source_eenheid_id=share.source_eenheid_id,
        target_eenheid_id=share.target_eenheid_id,
        access_level=share.access_level,
        shared_by_id=share.shared_by_id,
        reason=share.reason,
        geldig_van=share.geldig_van,
        geldig_tot=share.geldig_tot,
        created_at=share.created_at,
    )


@router.delete("/{share_id}")
async def revoke_share(
    share_id: UUID,
    _perm=Depends(require_permission("org:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a shared access grant."""
    repo = SharedAccessRepository(db)
    deleted = await repo.delete(share_id)
    if not deleted:
        raise HTTPException(404, "Share not found")
    return {"ok": True}
