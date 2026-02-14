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

_INDEXES = [
    # (index_name, table_name, columns)
    # activity - FK columns and created_at for time-range queries
    ("ix_activity_actor_id", "activity", ["actor_id"]),
    ("ix_activity_node_id", "activity", ["node_id"]),
    ("ix_activity_task_id", "activity", ["task_id"]),
    ("ix_activity_edge_id", "activity", ["edge_id"]),
    ("ix_activity_created_at", "activity", ["created_at"]),
    # node_tag - tag_id (node_id covered by existing unique constraint)
    ("ix_node_tag_tag_id", "node_tag", ["tag_id"]),
    # notification - FK columns, thread lookups, reaction dedup
    ("ix_notification_person_id", "notification", ["person_id"]),
    ("ix_notification_parent_id", "notification", ["parent_id"]),
    ("ix_notification_sender_id", "notification", ["sender_id"]),
    ("ix_notification_thread_id", "notification", ["thread_id"]),
    # parlementair_item - review queue filtering
    (
        "ix_parlementair_item_corpus_node_id",
        "parlementair_item",
        ["corpus_node_id"],
    ),
    ("ix_parlementair_item_status", "parlementair_item", ["status"]),
    ("ix_parlementair_item_type", "parlementair_item", ["type"]),
    # suggested_edge - edge review queries
    (
        "ix_suggested_edge_parlementair_item_id",
        "suggested_edge",
        ["parlementair_item_id"],
    ),
    (
        "ix_suggested_edge_target_node_id",
        "suggested_edge",
        ["target_node_id"],
    ),
    ("ix_suggested_edge_status", "suggested_edge", ["status"]),
    # corpus_node_title - temporal title history lookups
    ("ix_corpus_node_title_node_id", "corpus_node_title", ["node_id"]),
    # corpus_node_status - temporal status history lookups
    (
        "ix_corpus_node_status_node_id",
        "corpus_node_status",
        ["node_id"],
    ),
    # organisatie_eenheid_naam - org name history
    (
        "ix_organisatie_eenheid_naam_eenheid_id",
        "organisatie_eenheid_naam",
        ["eenheid_id"],
    ),
    # organisatie_eenheid_parent - org tree traversal
    (
        "ix_organisatie_eenheid_parent_eenheid_id",
        "organisatie_eenheid_parent",
        ["eenheid_id"],
    ),
    (
        "ix_organisatie_eenheid_parent_parent_id",
        "organisatie_eenheid_parent",
        ["parent_id"],
    ),
    # organisatie_eenheid_manager - manager lookups
    (
        "ix_organisatie_eenheid_manager_eenheid_id",
        "organisatie_eenheid_manager",
        ["eenheid_id"],
    ),
    (
        "ix_organisatie_eenheid_manager_manager_id",
        "organisatie_eenheid_manager",
        ["manager_id"],
    ),
]


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(
            name, table, columns, if_not_exists=True
        )


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
