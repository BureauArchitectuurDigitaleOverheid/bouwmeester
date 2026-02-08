"""merge motie_import_task and person_refactor_indexes

Revision ID: 03bc23d0b7e2
Revises: 66dd28885049, 74f8addb8848
Create Date: 2026-02-08 19:51:04.541141

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "03bc23d0b7e2"
down_revision: str | None = ("66dd28885049", "74f8addb8848")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
