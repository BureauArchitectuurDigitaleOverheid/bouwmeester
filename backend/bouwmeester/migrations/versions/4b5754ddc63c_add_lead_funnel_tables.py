"""add lead funnel tables

Revision ID: 4b5754ddc63c
Revises: cee2c456b55d
Create Date: 2026-03-26 21:26:05.590273

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4b5754ddc63c"
down_revision: str | None = "cee2c456b55d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # externe_organisatie already exists (created in migration 233ab470df5d)

    op.create_table(
        "lead",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("organization", sa.String(), nullable=True),
        sa.Column("externe_organisatie_id", sa.UUID(), nullable=True),
        sa.Column(
            "stage",
            sa.String(),
            server_default="verkennen",
            nullable=False,
            comment="verkennen|eerste_gesprek|interne_check|follow_up|in_the_pocket|koelkast",
        ),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("next_action_date", sa.Date(), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSON(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_intake_text", sa.Text(), nullable=True),
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assignee_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["externe_organisatie_id"], ["externe_organisatie.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"], ["organisatie_eenheid.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lead_assignee_id"), "lead", ["assignee_id"], unique=False)
    op.create_index(
        op.f("ix_lead_organisatie_eenheid_id"),
        "lead",
        ["organisatie_eenheid_id"],
        unique=False,
    )

    op.create_table(
        "lead_activity",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "activity_type",
            sa.String(),
            server_default="note",
            nullable=False,
            comment="note|stage_change|meeting|call|email",
        ),
        sa.Column(
            "metadata",
            postgresql.JSON(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["author_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lead_activity_lead_id"), "lead_activity", ["lead_id"], unique=False
    )

    op.create_table(
        "lead_attachment",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("lead_id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lead_attachment_lead_id"), "lead_attachment", ["lead_id"], unique=False
    )

    op.create_table(
        "lead_contact",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column(
            "rol",
            sa.String(),
            server_default="contactpersoon",
            nullable=False,
            comment="contactpersoon|opdrachtgever|betrokken",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", "person_id", "rol", name="uq_lead_contact"),
    )
    op.create_index(
        op.f("ix_lead_contact_lead_id"), "lead_contact", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_lead_contact_person_id"), "lead_contact", ["person_id"], unique=False
    )

    op.create_table(
        "lead_node",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["corpus_node.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", "node_id", name="uq_lead_node"),
    )
    op.create_index(
        op.f("ix_lead_node_lead_id"), "lead_node", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_lead_node_node_id"), "lead_node", ["node_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lead_node_node_id"), table_name="lead_node")
    op.drop_index(op.f("ix_lead_node_lead_id"), table_name="lead_node")
    op.drop_table("lead_node")
    op.drop_index(op.f("ix_lead_contact_person_id"), table_name="lead_contact")
    op.drop_index(op.f("ix_lead_contact_lead_id"), table_name="lead_contact")
    op.drop_table("lead_contact")
    op.drop_index(op.f("ix_lead_attachment_lead_id"), table_name="lead_attachment")
    op.drop_table("lead_attachment")
    op.drop_index(op.f("ix_lead_activity_lead_id"), table_name="lead_activity")
    op.drop_table("lead_activity")
    op.drop_index(op.f("ix_lead_organisatie_eenheid_id"), table_name="lead")
    op.drop_index(op.f("ix_lead_assignee_id"), table_name="lead")
    op.drop_table("lead")
    # externe_organisatie not dropped here (owned by migration 233ab470df5d)
