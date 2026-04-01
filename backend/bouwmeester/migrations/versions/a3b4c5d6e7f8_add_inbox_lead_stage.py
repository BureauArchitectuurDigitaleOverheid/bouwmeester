"""Add inbox lead stage.

Revision ID: a3b4c5d6e7f8
Revises: 2d4ae903b0f0
Create Date: 2026-04-01
"""

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "2d4ae903b0f0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # stage is a plain varchar, not a PG enum -- just update defaults and comment.
    op.alter_column(
        "lead",
        "stage",
        server_default="inbox",
        comment="inbox|verkennen|eerste_gesprek|interne_check|follow_up|in_the_pocket|koelkast",
    )


def downgrade() -> None:
    op.alter_column(
        "lead",
        "stage",
        server_default="verkennen",
        comment="verkennen|eerste_gesprek|interne_check|follow_up|in_the_pocket|koelkast",
    )
