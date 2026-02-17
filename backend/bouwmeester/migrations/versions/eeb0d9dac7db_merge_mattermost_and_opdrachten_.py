"""merge mattermost and opdrachten migrations

Revision ID: eeb0d9dac7db
Revises: 233ab470df5d, ff993f2c1770
Create Date: 2026-02-17 07:06:58.855132

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "eeb0d9dac7db"
down_revision: str | None = ("233ab470df5d", "ff993f2c1770")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
