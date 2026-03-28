"""drop person is_admin column

Admin status is now fully determined by the person_role table
(role_id='super_admin'). The legacy is_admin column on the person
table is no longer read or written.

Revision ID: a1b2c3d4e5f6
Revises: 724a3a1f3435
Create Date: 2026-03-28 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "724a3a1f3435"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("person", "is_admin")


def downgrade() -> None:
    op.add_column(
        "person",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
