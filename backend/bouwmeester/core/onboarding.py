"""Modular onboarding feature registry.

Each onboarding feature defines:
- how to check if it is completed (computed from existing data)
- whether it can be dismissed by the user
- whether it is currently enabled (e.g. Mattermost may be off)

The registry is the single source of truth for which onboarding steps
exist and in what order they are presented.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.models.onboarding_dismissal import OnboardingDismissal
from bouwmeester.models.person import Person

# Type alias for async check functions.
CheckFn = Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]


@dataclass
class OnboardingFeature:
    key: str
    label: str
    order: int
    dismissible: bool
    check_complete: CheckFn
    check_enabled: CheckFn | None = field(default=None)
    blocking: bool = field(default=True)


# ---------------------------------------------------------------------------
# Completion checks
# ---------------------------------------------------------------------------


async def _profile_complete(db: AsyncSession, person_id: uuid.UUID) -> bool:
    result = await db.execute(select(Person.functie).where(Person.id == person_id))
    functie = result.scalar_one_or_none()
    return bool(functie)


async def _mattermost_complete(db: AsyncSession, person_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(MattermostUser.id).where(MattermostUser.person_id == person_id)
    )
    return result.scalar_one_or_none() is not None


async def _intro_handleiding_complete(_db: AsyncSession, _person_id: uuid.UUID) -> bool:
    """Informational — never auto-completes; must be dismissed."""
    return False


# ---------------------------------------------------------------------------
# Enabled checks
# ---------------------------------------------------------------------------


async def _mattermost_enabled(db: AsyncSession, _person_id: uuid.UUID) -> bool:
    """Check whether Mattermost integration is turned on."""
    from bouwmeester.services.mattermost_service import MattermostService

    svc = MattermostService(db)
    return await svc.is_enabled()


# ---------------------------------------------------------------------------
# Feature registry
# ---------------------------------------------------------------------------

ONBOARDING_FEATURES: list[OnboardingFeature] = [
    OnboardingFeature(
        key="profile",
        label="Profiel",
        order=10,
        dismissible=False,
        check_complete=_profile_complete,
    ),
    OnboardingFeature(
        key="mattermost",
        label="Mattermost",
        order=20,
        dismissible=True,
        check_complete=_mattermost_complete,
        check_enabled=_mattermost_enabled,
    ),
    OnboardingFeature(
        key="intro_handleiding",
        label="Introductie",
        order=100,
        dismissible=True,
        check_complete=_intro_handleiding_complete,
        blocking=False,
    ),
]

_FEATURES_BY_KEY: dict[str, OnboardingFeature] = {f.key: f for f in ONBOARDING_FEATURES}


def get_feature(key: str) -> OnboardingFeature | None:
    return _FEATURES_BY_KEY.get(key)


async def get_pending_onboarding_features(
    db: AsyncSession,
    person_id: uuid.UUID,
    session_dismissed: set[str] | None = None,
) -> list[dict]:
    """Return the list of onboarding features that still need attention.

    Features are skipped when:
    - not enabled (check_enabled returns False)
    - already completed (check_complete returns True)
    - dismissed in this session (session_dismissed)
    - permanently dismissed (onboarding_dismissal table)
    """
    if session_dismissed is None:
        session_dismissed = set()

    # Fetch all permanent dismissals for this person in one query.
    result = await db.execute(
        select(OnboardingDismissal.feature_key).where(
            OnboardingDismissal.person_id == person_id
        )
    )
    permanent_dismissed = {row[0] for row in result.all()}

    pending: list[dict] = []
    for feature in sorted(ONBOARDING_FEATURES, key=lambda f: f.order):
        # Skip disabled features.
        if feature.check_enabled is not None:
            if not await feature.check_enabled(db, person_id):
                continue

        # Skip completed features.
        if await feature.check_complete(db, person_id):
            continue

        # Skip dismissed features (session or permanent).
        if feature.key in session_dismissed or feature.key in permanent_dismissed:
            continue

        pending.append(
            {
                "key": feature.key,
                "label": feature.label,
                "dismissible": feature.dismissible,
                "blocking": feature.blocking,
            }
        )

    return pending
