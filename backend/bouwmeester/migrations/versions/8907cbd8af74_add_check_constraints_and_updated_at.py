"""add check constraints, externe_organisatie updated_at, and task.opdracht_id

Revision ID: 8907cbd8af74
Revises: eeb0d9dac7db
Create Date: 2026-02-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8907cbd8af74"
down_revision: str | None = "eeb0d9dac7db"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Check constraints for opdracht
    op.create_check_constraint(
        "ck_opdracht_type",
        "opdracht",
        "type IN ('opdracht', 'subsidie')",
    )
    op.create_check_constraint(
        "ck_opdracht_status",
        "opdracht",
        "status IN ('concept', 'actief', 'afgerond', 'verantwoord', 'geannuleerd')",
    )
    op.create_check_constraint(
        "ck_opdracht_kostensoort",
        "opdracht",
        "kostensoort IS NULL OR kostensoort IN "
        "('investering', 'exploitatie', 'gemengd')",
    )

    # Non-negative check constraints for financial fields
    op.create_check_constraint(
        "ck_opdracht_budget_nonneg",
        "opdracht",
        "budget IS NULL OR budget >= 0",
    )
    op.create_check_constraint(
        "ck_opdracht_gerealiseerd_nonneg",
        "opdracht",
        "gerealiseerd IS NULL OR gerealiseerd >= 0",
    )
    op.create_check_constraint(
        "ck_opdracht_volgend_jaar_benodigd_nonneg",
        "opdracht",
        "volgend_jaar_benodigd IS NULL OR volgend_jaar_benodigd >= 0",
    )
    op.create_check_constraint(
        "ck_opdracht_volgend_jaar_aangevraagd_nonneg",
        "opdracht",
        "volgend_jaar_aangevraagd IS NULL OR volgend_jaar_aangevraagd >= 0",
    )

    # Check constraint for opdracht_node
    op.create_check_constraint(
        "ck_opdracht_node_relatie_type",
        "opdracht_node",
        "relatie_type IN ('bekostigt', 'draagt_bij_aan')",
    )

    # Check constraint for externe_organisatie
    op.create_check_constraint(
        "ck_externe_organisatie_type",
        "externe_organisatie",
        "type IN ('uitvoeringsorganisatie', 'zbo', 'koepelorganisatie', "
        "'stichting', 'marktpartij', 'overig')",
    )

    # Unique constraint on externe_organisatie.naam
    op.create_unique_constraint(
        "uq_externe_organisatie_naam",
        "externe_organisatie",
        ["naam"],
    )

    # Add updated_at to externe_organisatie
    op.add_column(
        "externe_organisatie",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Add opdracht_id FK to task
    op.add_column(
        "task",
        sa.Column(
            "opdracht_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index("ix_task_opdracht_id", "task", ["opdracht_id"])
    op.create_foreign_key(
        "fk_task_opdracht_id",
        "task",
        "opdracht",
        ["opdracht_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_task_opdracht_id", "task", type_="foreignkey")
    op.drop_index("ix_task_opdracht_id", table_name="task")
    op.drop_column("task", "opdracht_id")
    op.drop_column("externe_organisatie", "updated_at")
    op.drop_constraint(
        "uq_externe_organisatie_naam", "externe_organisatie", type_="unique"
    )
    op.drop_constraint(
        "ck_externe_organisatie_type", "externe_organisatie", type_="check"
    )
    op.drop_constraint("ck_opdracht_node_relatie_type", "opdracht_node", type_="check")
    op.drop_constraint("ck_opdracht_kostensoort", "opdracht", type_="check")
    op.drop_constraint("ck_opdracht_status", "opdracht", type_="check")
    op.drop_constraint("ck_opdracht_type", "opdracht", type_="check")
    op.drop_constraint("ck_opdracht_budget_nonneg", "opdracht", type_="check")
    op.drop_constraint("ck_opdracht_gerealiseerd_nonneg", "opdracht", type_="check")
    op.drop_constraint(
        "ck_opdracht_volgend_jaar_benodigd_nonneg", "opdracht", type_="check"
    )
    op.drop_constraint(
        "ck_opdracht_volgend_jaar_aangevraagd_nonneg", "opdracht", type_="check"
    )
