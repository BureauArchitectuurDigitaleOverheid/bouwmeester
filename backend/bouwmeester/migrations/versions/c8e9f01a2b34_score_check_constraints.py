"""add CHECK constraints on funnel + assessment scores

Revision ID: c8e9f01a2b34
Revises: 7f9793c38f23
Create Date: 2026-05-05

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c8e9f01a2b34"
down_revision: str | None = "7f9793c38f23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lead funnel scores
    for col in ("score_strategisch", "score_politiek", "score_positie"):
        op.create_check_constraint(
            f"ck_lead_{col}_range",
            "lead",
            f"{col} IS NULL OR ({col} BETWEEN 1 AND 5)",
        )
    # Stakeholder assessment scores
    for col in ("belang", "invloed"):
        op.create_check_constraint(
            f"ck_stakeholder_assessment_{col}_range",
            "stakeholder_assessment",
            f"{col} IS NULL OR ({col} BETWEEN 1 AND 5)",
        )


def downgrade() -> None:
    for col in ("belang", "invloed"):
        op.drop_constraint(
            f"ck_stakeholder_assessment_{col}_range",
            "stakeholder_assessment",
            type_="check",
        )
    for col in ("score_strategisch", "score_politiek", "score_positie"):
        op.drop_constraint(f"ck_lead_{col}_range", "lead", type_="check")
