"""add organisatie_eenheid_id to corpus_node

Revision ID: 16ecb93b7508
Revises: 0ffaf9913d8d
Create Date: 2026-03-27 06:30:52.823117

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16ecb93b7508"
down_revision: Union[str, None] = "0ffaf9913d8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "corpus_node",
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_corpus_node_organisatie_eenheid_id"),
        "corpus_node",
        ["organisatie_eenheid_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_corpus_node_organisatie_eenheid",
        "corpus_node",
        "organisatie_eenheid",
        ["organisatie_eenheid_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_corpus_node_organisatie_eenheid", "corpus_node", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_corpus_node_organisatie_eenheid_id"), table_name="corpus_node"
    )
    op.drop_column("corpus_node", "organisatie_eenheid_id")
