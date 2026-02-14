"""add missing FK indexes

Revision ID: 025becdecf77
Revises: 7ea63555fee6
Create Date: 2026-02-14 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025becdecf77"
down_revision: str | None = "7ea63555fee6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # activity - FK columns and created_at for time-range queries
    op.create_index("ix_activity_actor_id", "activity", ["actor_id"])
    op.create_index("ix_activity_node_id", "activity", ["node_id"])
    op.create_index("ix_activity_task_id", "activity", ["task_id"])
    op.create_index("ix_activity_edge_id", "activity", ["edge_id"])
    op.create_index("ix_activity_created_at", "activity", ["created_at"])

    # node_tag - tag_id (node_id covered by existing unique constraint)
    op.create_index("ix_node_tag_tag_id", "node_tag", ["tag_id"])

    # notification - FK columns for queries, thread lookups, reaction dedup
    op.create_index("ix_notification_person_id", "notification", ["person_id"])
    op.create_index("ix_notification_parent_id", "notification", ["parent_id"])
    op.create_index("ix_notification_sender_id", "notification", ["sender_id"])
    op.create_index("ix_notification_thread_id", "notification", ["thread_id"])

    # parlementair_item - review queue filtering
    op.create_index(
        "ix_parlementair_item_corpus_node_id",
        "parlementair_item",
        ["corpus_node_id"],
    )
    op.create_index("ix_parlementair_item_status", "parlementair_item", ["status"])
    op.create_index("ix_parlementair_item_type", "parlementair_item", ["type"])

    # suggested_edge - edge review queries
    op.create_index(
        "ix_suggested_edge_parlementair_item_id",
        "suggested_edge",
        ["parlementair_item_id"],
    )
    op.create_index(
        "ix_suggested_edge_target_node_id",
        "suggested_edge",
        ["target_node_id"],
    )
    op.create_index("ix_suggested_edge_status", "suggested_edge", ["status"])

    # corpus_node_title - temporal title history lookups
    op.create_index(
        "ix_corpus_node_title_node_id", "corpus_node_title", ["node_id"]
    )

    # corpus_node_status - temporal status history lookups
    op.create_index(
        "ix_corpus_node_status_node_id", "corpus_node_status", ["node_id"]
    )

    # organisatie_eenheid_naam - org name history
    op.create_index(
        "ix_organisatie_eenheid_naam_eenheid_id",
        "organisatie_eenheid_naam",
        ["eenheid_id"],
    )

    # organisatie_eenheid_parent - org tree traversal
    op.create_index(
        "ix_organisatie_eenheid_parent_eenheid_id",
        "organisatie_eenheid_parent",
        ["eenheid_id"],
    )
    op.create_index(
        "ix_organisatie_eenheid_parent_parent_id",
        "organisatie_eenheid_parent",
        ["parent_id"],
    )

    # organisatie_eenheid_manager - manager lookups
    op.create_index(
        "ix_organisatie_eenheid_manager_eenheid_id",
        "organisatie_eenheid_manager",
        ["eenheid_id"],
    )
    op.create_index(
        "ix_organisatie_eenheid_manager_manager_id",
        "organisatie_eenheid_manager",
        ["manager_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_organisatie_eenheid_manager_manager_id")
    op.drop_index("ix_organisatie_eenheid_manager_eenheid_id")
    op.drop_index("ix_organisatie_eenheid_parent_parent_id")
    op.drop_index("ix_organisatie_eenheid_parent_eenheid_id")
    op.drop_index("ix_organisatie_eenheid_naam_eenheid_id")
    op.drop_index("ix_corpus_node_status_node_id")
    op.drop_index("ix_corpus_node_title_node_id")
    op.drop_index("ix_suggested_edge_status")
    op.drop_index("ix_suggested_edge_target_node_id")
    op.drop_index("ix_suggested_edge_parlementair_item_id")
    op.drop_index("ix_parlementair_item_type")
    op.drop_index("ix_parlementair_item_status")
    op.drop_index("ix_parlementair_item_corpus_node_id")
    op.drop_index("ix_notification_thread_id")
    op.drop_index("ix_notification_sender_id")
    op.drop_index("ix_notification_parent_id")
    op.drop_index("ix_notification_person_id")
    op.drop_index("ix_node_tag_tag_id")
    op.drop_index("ix_activity_created_at")
    op.drop_index("ix_activity_edge_id")
    op.drop_index("ix_activity_task_id")
    op.drop_index("ix_activity_node_id")
    op.drop_index("ix_activity_actor_id")
