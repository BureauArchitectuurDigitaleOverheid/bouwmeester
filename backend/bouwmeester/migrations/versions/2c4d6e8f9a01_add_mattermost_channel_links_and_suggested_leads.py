"""add mattermost channel links, post links, suggested leads + lead_attachment url type

Revision ID: 2c4d6e8f9a01
Revises: a1f3c8e7d402
Create Date: 2026-05-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2c4d6e8f9a01"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- mattermost_channel_link -----
    op.create_table(
        "mattermost_channel_link",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(length=26), nullable=False),
        sa.Column("channel_name", sa.String(length=255), nullable=False),
        sa.Column("channel_display_name", sa.String(length=255), nullable=False),
        sa.Column("team_id", sa.String(length=26), nullable=True),
        sa.Column(
            "scope_type",
            sa.String(length=32),
            nullable=False,
            comment="initiatief|lead",
        ),
        sa.Column("scope_id", sa.UUID(), nullable=False),
        sa.Column(
            "auto_note_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "suggest_leads_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "last_seen_post_at",
            sa.BigInteger(),
            nullable=True,
            comment=(
                "Mattermost ms-timestamp van laatst verwerkte post "
                "(recovery na reconnect)"
            ),
        ),
        sa.Column(
            "disabled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Bot is uit kanaal getrapt of kanaal is verwijderd",
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id"),
    )
    op.create_index(
        "ix_mattermost_channel_link_channel_id",
        "mattermost_channel_link",
        ["channel_id"],
    )
    op.create_index(
        "ix_mattermost_channel_link_scope_id",
        "mattermost_channel_link",
        ["scope_id"],
    )

    # ----- suggested_lead -----
    op.create_table(
        "suggested_lead",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.String(length=32),
            server_default="mattermost",
            nullable=False,
        ),
        sa.Column("source_post_id", sa.String(length=26), nullable=False),
        sa.Column("source_channel_id", sa.String(length=26), nullable=False),
        sa.Column("source_root_id", sa.String(length=26), nullable=True),
        sa.Column("initiatief_id", sa.UUID(), nullable=False),
        sa.Column("proposed_title", sa.String(length=500), nullable=False),
        sa.Column("proposed_description", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("match_existing_lead_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
            comment="pending|approved_new|approved_linked|rejected",
        ),
        sa.Column(
            "mm_thread_post_id",
            sa.String(length=26),
            nullable=True,
            comment="Bot-reply-post met de approval-knoppen, voor latere edit",
        ),
        sa.Column("approved_lead_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "review_source",
            sa.String(length=32),
            nullable=True,
            comment="mattermost|ui",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["initiatief_id"], ["initiatief.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["match_existing_lead_id"], ["lead.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["approved_lead_id"], ["lead.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_suggested_lead_initiatief_id", "suggested_lead", ["initiatief_id"]
    )
    op.create_index("ix_suggested_lead_status", "suggested_lead", ["status"])

    # ----- mattermost_post_link -----
    op.create_table(
        "mattermost_post_link",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("post_id", sa.String(length=26), nullable=False),
        sa.Column("channel_id", sa.String(length=26), nullable=False),
        sa.Column("root_id", sa.String(length=26), nullable=True),
        sa.Column(
            "scope_type",
            sa.String(length=32),
            nullable=False,
            comment="initiatief|lead",
        ),
        sa.Column("scope_id", sa.UUID(), nullable=False),
        sa.Column("lead_activity_id", sa.UUID(), nullable=True),
        sa.Column("suggested_lead_id", sa.UUID(), nullable=True),
        sa.Column("mm_user_id", sa.String(length=26), nullable=True),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column(
            "skipped_reason",
            sa.String(length=64),
            nullable=True,
            comment="bot_self|noise|no_link|other — voor diagnose",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_activity_id"], ["lead_activity.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["suggested_lead_id"], ["suggested_lead.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id"),
    )
    op.create_index(
        "ix_mattermost_post_link_post_id", "mattermost_post_link", ["post_id"]
    )
    op.create_index(
        "ix_mattermost_post_link_channel_id", "mattermost_post_link", ["channel_id"]
    )
    op.create_index(
        "ix_mattermost_post_link_scope_id", "mattermost_post_link", ["scope_id"]
    )

    # ----- lead_attachment: url-type velden -----
    op.add_column(
        "lead_attachment",
        sa.Column(
            "soort",
            sa.String(),
            nullable=False,
            server_default="file",
            comment="file|link",
        ),
    )
    op.add_column("lead_attachment", sa.Column("url", sa.String(), nullable=True))
    op.add_column(
        "lead_attachment",
        sa.Column(
            "source",
            sa.String(),
            nullable=False,
            server_default="upload",
            comment="upload|mattermost",
        ),
    )
    op.add_column(
        "lead_attachment",
        sa.Column(
            "source_ref",
            sa.String(),
            nullable=True,
            comment="bv. mattermost post_id",
        ),
    )
    # File-velden worden nullable zodat URL-attachments zonder pad/grootte kunnen.
    op.alter_column(
        "lead_attachment", "bestandsnaam", existing_type=sa.String(), nullable=True
    )
    op.alter_column(
        "lead_attachment", "content_type", existing_type=sa.String(), nullable=True
    )
    op.alter_column(
        "lead_attachment",
        "bestandsgrootte",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column("lead_attachment", "pad", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("lead_attachment", "pad", existing_type=sa.String(), nullable=False)
    op.alter_column(
        "lead_attachment",
        "bestandsgrootte",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "lead_attachment", "content_type", existing_type=sa.String(), nullable=False
    )
    op.alter_column(
        "lead_attachment", "bestandsnaam", existing_type=sa.String(), nullable=False
    )
    op.drop_column("lead_attachment", "source_ref")
    op.drop_column("lead_attachment", "source")
    op.drop_column("lead_attachment", "url")
    op.drop_column("lead_attachment", "soort")

    op.drop_index("ix_mattermost_post_link_scope_id", table_name="mattermost_post_link")
    op.drop_index(
        "ix_mattermost_post_link_channel_id", table_name="mattermost_post_link"
    )
    op.drop_index("ix_mattermost_post_link_post_id", table_name="mattermost_post_link")
    op.drop_table("mattermost_post_link")

    op.drop_index("ix_suggested_lead_status", table_name="suggested_lead")
    op.drop_index("ix_suggested_lead_initiatief_id", table_name="suggested_lead")
    op.drop_table("suggested_lead")

    op.drop_index(
        "ix_mattermost_channel_link_scope_id", table_name="mattermost_channel_link"
    )
    op.drop_index(
        "ix_mattermost_channel_link_channel_id", table_name="mattermost_channel_link"
    )
    op.drop_table("mattermost_channel_link")
