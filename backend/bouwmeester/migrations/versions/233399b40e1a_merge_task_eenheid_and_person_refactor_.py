"""merge task eenheid and person refactor branches

Revision ID: 233399b40e1a
Revises: 2442ad1cfef7, e89fa2717ecf
Create Date: 2026-02-08 17:29:56.224717

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "233399b40e1a"
down_revision: str | None = ("2442ad1cfef7", "e89fa2717ecf")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
