"""merge bron and access_request migrations

Revision ID: 6fc2b9738eea
Revises: 408967f9dc7c, fe6396acfb0b
Create Date: 2026-02-12 20:06:07.196807

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6fc2b9738eea"
down_revision: tuple[str, str] = ("408967f9dc7c", "fe6396acfb0b")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
