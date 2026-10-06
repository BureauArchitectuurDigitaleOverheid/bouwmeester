"""Remember who said what became of a marked question, and when

People who follow a debate put a reaction on the reply of a question:
answered, picked up, needs no answer, not a question. The status column was
there already. What is added is whose reaction decided it and since when,
and a mark for "the reactions on this reply changed": the websocket sets
it, the round of the questions reads the reactions and writes the result.

The index on `thread_post_id` is for the websocket: every reaction in every
channel asks whether its post is the reply of a markering.

Revision ID: e3b5c7d92f46
Revises: e3b5c7d9f1a2
Create Date: 2026-10-06

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3b5c7d92f46"
down_revision: str | None = "e3b5c7d9f1a2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Whether the reply of this markering carries the note that goes under
    # the first reply of a thread, so that a reply that is written again
    # (for its status) keeps it or keeps being without it.
    op.add_column(
        "debat_markering",
        sa.Column(
            "met_noot", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    # The replies that are in a channel already were posted before this was
    # kept. Without this, the first time one of them is written again for a
    # status its thread would lose the note. Which reply got in first is
    # not known any more; the lowest number under a message is the best
    # guess, and at worst the note moves one reply.
    op.execute(
        """
        UPDATE debat_markering
        SET met_noot = true
        WHERE id IN (
            SELECT DISTINCT ON (beurt_post_id) id
            FROM debat_markering
            WHERE thread_post_id IS NOT NULL AND beurt_post_id IS NOT NULL
            ORDER BY beurt_post_id, volgnummer
        )
        """
    )
    op.add_column(
        "debat_markering",
        sa.Column("status_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "debat_markering",
        sa.Column(
            "status_door_mattermost_user_id", sa.String(length=26), nullable=True
        ),
    )
    op.add_column(
        "debat_markering",
        sa.Column(
            "status_door_person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "person.id",
                name="fk_debat_markering_status_door_person_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "debat_markering",
        sa.Column("reacties_gewijzigd_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_debat_markering_thread_post_id", "debat_markering", ["thread_post_id"]
    )
    op.create_index(
        "ix_debat_markering_status_door_person_id",
        "debat_markering",
        ["status_door_person_id"],
    )
    op.create_index(
        "ix_debat_markering_reacties_gewijzigd_at",
        "debat_markering",
        ["reacties_gewijzigd_at"],
        postgresql_where=sa.text("reacties_gewijzigd_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_column("debat_markering", "met_noot")
    op.drop_index("ix_debat_markering_reacties_gewijzigd_at", "debat_markering")
    op.drop_index("ix_debat_markering_status_door_person_id", "debat_markering")
    op.drop_index("ix_debat_markering_thread_post_id", "debat_markering")
    op.drop_column("debat_markering", "reacties_gewijzigd_at")
    op.drop_constraint(
        "fk_debat_markering_status_door_person_id",
        "debat_markering",
        type_="foreignkey",
    )
    op.drop_column("debat_markering", "status_door_person_id")
    op.drop_column("debat_markering", "status_door_mattermost_user_id")
    op.drop_column("debat_markering", "status_at")
