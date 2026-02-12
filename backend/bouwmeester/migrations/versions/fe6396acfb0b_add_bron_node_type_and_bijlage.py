"""add bron node type and bijlage

Revision ID: fe6396acfb0b
Revises: bcfeec6929b2
Create Date: 2026-02-12 17:57:35.941949

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fe6396acfb0b"
down_revision: Union[str, None] = "bcfeec6929b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bron",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "type",
            sa.String(),
            server_default="overig",
            nullable=False,
            comment="rapport|onderzoek|wetgeving|advies|opinie|beleidsnota|evaluatie|overig",
        ),
        sa.Column("auteur", sa.String(), nullable=True),
        sa.Column("publicatie_datum", sa.Date(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["corpus_node.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bron_bijlage",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("bron_id", sa.UUID(), nullable=False),
        sa.Column("bestandsnaam", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("bestandsgrootte", sa.Integer(), nullable=False),
        sa.Column("pad", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bron_id"], ["bron.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("bron_bijlage")
    op.drop_table("bron")
