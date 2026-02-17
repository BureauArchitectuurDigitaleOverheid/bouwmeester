"""add check constraints and externe_organisatie updated_at

Revision ID: a1b2c3d4e5f6
Revises: eeb0d9dac7db
Create Date: 2026-02-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
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
        "kostensoort IS NULL OR kostensoort IN ('investering', 'exploitatie', 'gemengd')",
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

    # Add updated_at to externe_organisatie
    op.add_column(
        "externe_organisatie",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("externe_organisatie", "updated_at")
    op.drop_constraint("ck_externe_organisatie_type", "externe_organisatie", type_="check")
    op.drop_constraint("ck_opdracht_node_relatie_type", "opdracht_node", type_="check")
    op.drop_constraint("ck_opdracht_kostensoort", "opdracht", type_="check")
    op.drop_constraint("ck_opdracht_status", "opdracht", type_="check")
    op.drop_constraint("ck_opdracht_type", "opdracht", type_="check")
