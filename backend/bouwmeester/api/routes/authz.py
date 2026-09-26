"""AuthZEN-shaped evaluation endpoint: may the caller do these actions?

The frontend asks here instead of re-deriving rights from roles, so buttons
match what the API will allow.  Every answer comes from ``core.authz.can``;
a missing resource is ``false`` just like a forbidden one, so this endpoint
reveals no more than ``can()`` does.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.schema.authz import (
    AuthzDecision,
    AuthzEvaluationsRequest,
    AuthzEvaluationsResponse,
)

router = APIRouter(prefix="/authz", tags=["authz"])


@router.post("/evaluations", response_model=AuthzEvaluationsResponse)
async def evaluate(
    data: AuthzEvaluationsRequest,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> AuthzEvaluationsResponse:
    """Decide each evaluation for the caller, in order."""
    decisions = []
    for evaluation in data.evaluations:
        resource = evaluation.resource
        eenheid_id = resource.properties.eenheid_id if resource.properties else None
        try:
            decision = await can(
                db,
                perm_ctx,
                evaluation.action,
                resource.type,
                resource.id,
                eenheid_id=eenheid_id,
            )
        except ValueError:
            # A question can() does not decide (an existing person): no.
            decision = False
        decisions.append(AuthzDecision(decision=decision))
    return AuthzEvaluationsResponse(evaluations=decisions)
