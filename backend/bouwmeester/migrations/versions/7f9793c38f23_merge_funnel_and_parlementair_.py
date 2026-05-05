"""merge funnel and parlementair-permissions heads

Revision ID: 7f9793c38f23
Revises: 27276a028617, b6d7e8f90135
Create Date: 2026-05-05 07:35:07.769970

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7f9793c38f23"
down_revision: str | None = ("27276a028617", "b6d7e8f90135")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
