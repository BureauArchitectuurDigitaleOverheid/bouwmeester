"""add indices on person_organisatie_eenheid FK columns

Revision ID: f18d6788fcc0
Revises: 97ccf3b922b4
Create Date: 2026-02-13 06:54:10.269211

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f18d6788fcc0"
down_revision: Union[str, None] = "97ccf3b922b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_person_organisatie_eenheid_person_id"),
        "person_organisatie_eenheid",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_person_organisatie_eenheid_organisatie_eenheid_id"),
        "person_organisatie_eenheid",
        ["organisatie_eenheid_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_person_organisatie_eenheid_organisatie_eenheid_id"),
        table_name="person_organisatie_eenheid",
    )
    op.drop_index(
        op.f("ix_person_organisatie_eenheid_person_id"),
        table_name="person_organisatie_eenheid",
    )
