"""drop team and team_member tables

Revision ID: aec85cc29d54
Revises: a3f1e8c7d920
Create Date: 2026-03-29 10:46:00.412097

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aec85cc29d54"
down_revision: str | None = "a3f1e8c7d920"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clean up any resource_permission rows referencing "team"
    op.execute("DELETE FROM resource_permission WHERE resource_type = 'team'")
    # Drop child table first (FK to team)
    op.drop_table("team_member")
    op.drop_table("team")


def downgrade() -> None:
    op.create_table(
        "team",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("naam", sa.String(), nullable=False),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_member",
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column(
            "rol",
            sa.String(),
            server_default="lid",
            nullable=False,
            comment="lid|coordinator",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["team.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", "person_id"),
    )
