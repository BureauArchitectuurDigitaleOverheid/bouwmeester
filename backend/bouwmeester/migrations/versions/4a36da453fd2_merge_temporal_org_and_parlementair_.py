"""merge temporal org and parlementair branches

Revision ID: 4a36da453fd2
Revises: 95d48f56f750, f01b49dfb7ef
Create Date: 2026-02-09 10:10:54.941641

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "4a36da453fd2"
down_revision: str | None = ("95d48f56f750", "f01b49dfb7ef")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
