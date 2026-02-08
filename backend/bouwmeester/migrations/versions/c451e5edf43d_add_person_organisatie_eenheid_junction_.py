"""add person organisatie eenheid junction table

Revision ID: c451e5edf43d
Revises: a091233f3214
Create Date: 2026-02-08 16:37:53.910625

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c451e5edf43d"
down_revision: str | None = "a091233f3214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create junction table
    op.create_table(
        "person_organisatie_eenheid",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=False),
        sa.Column(
            "dienstverband",
            sa.String(),
            server_default="in_dienst",
            nullable=False,
            comment="in_dienst|ingehuurd|extern",
        ),
        sa.Column("start_datum", sa.Date(), nullable=False),
        sa.Column("eind_datum", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"],
            ["organisatie_eenheid.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Migrate existing data: create a placement for each person with an org unit
    op.execute(
        """
        INSERT INTO person_organisatie_eenheid
            (person_id, organisatie_eenheid_id, dienstverband, start_datum)
        SELECT id, organisatie_eenheid_id, 'in_dienst', created_at::date
        FROM person
        WHERE organisatie_eenheid_id IS NOT NULL
        """
    )

    # Drop old FK and column
    op.drop_constraint("fk_person_organisatie_eenheid", "person", type_="foreignkey")
    op.drop_column("person", "organisatie_eenheid_id")


def downgrade() -> None:
    op.add_column(
        "person",
        sa.Column(
            "organisatie_eenheid_id",
            sa.UUID(),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_person_organisatie_eenheid",
        "person",
        "organisatie_eenheid",
        ["organisatie_eenheid_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Migrate back: pick the most recent active placement per person
    op.execute(
        """
        UPDATE person p SET organisatie_eenheid_id = (
            SELECT organisatie_eenheid_id
            FROM person_organisatie_eenheid poe
            WHERE poe.person_id = p.id AND poe.eind_datum IS NULL
            ORDER BY poe.start_datum DESC
            LIMIT 1
        )
        """
    )
    op.drop_table("person_organisatie_eenheid")
