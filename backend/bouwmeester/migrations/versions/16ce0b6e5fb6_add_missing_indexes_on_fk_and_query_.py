"""add missing indexes on FK and query columns

Revision ID: 16ce0b6e5fb6
Revises: f7e8d9c0b1a2
Create Date: 2026-03-27 13:29:41.930588

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16ce0b6e5fb6"
down_revision: str | None = "f7e8d9c0b1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All indexes use IF NOT EXISTS so the migration is idempotent.


def upgrade() -> None:
    # -- FK columns: high priority (queried in WHERE clauses) --
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_absence_person_id"
        " ON absence (person_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_absence_substitute_id"
        " ON absence (substitute_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_externe_organisatie_id"
        " ON lead (externe_organisatie_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_activity_author_id"
        " ON lead_activity (author_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_opdracht_opdrachtnemer_id"
        " ON opdracht (opdrachtnemer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_opdracht_opdrachtgever_id"
        " ON opdracht (opdrachtgever_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_opdracht_verantwoordelijke_id"
        " ON opdracht (verantwoordelijke_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_related_node_id"
        " ON notification (related_node_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_related_task_id"
        " ON notification (related_task_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_organisatie_eenheid_parent_id"
        " ON organisatie_eenheid (parent_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_organisatie_eenheid_manager_id"
        " ON organisatie_eenheid (manager_id)"
    )

    # -- FK columns: medium priority (CASCADE performance) --
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_access_request_reviewed_by_id"
        " ON access_request (reviewed_by_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_suggested_edge_edge_id"
        " ON suggested_edge (edge_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_suggested_edge_edge_type_id"
        " ON suggested_edge (edge_type_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_suggested_edge_reviewed_by"
        " ON suggested_edge (reviewed_by)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parlementair_item_reviewed_by"
        " ON parlementair_item (reviewed_by)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tag_parent_id"
        " ON tag (parent_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mattermost_link_code_person_id"
        " ON mattermost_link_code (person_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_opdracht_node_node_id"
        " ON opdracht_node (node_id)"
    )

    # -- Query-pattern indexes (WHERE / ORDER BY / search) --
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_stage"
        " ON lead (stage)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_next_action_date"
        " ON lead (next_action_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_created_at"
        " ON lead (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_activity_created_at"
        " ON lead_activity (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_title_trgm"
        " ON lead USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_status"
        " ON task (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_deadline"
        " ON task (deadline)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_unread"
        " ON notification (person_id, is_read)"
        " WHERE is_read = false"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_type_reaction"
        " ON notification (type)"
        " WHERE type = 'emoji_reaction'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parlementair_item_bron"
        " ON parlementair_item (bron)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parlementair_item_bron")
    op.execute("DROP INDEX IF EXISTS ix_notification_type_reaction")
    op.execute("DROP INDEX IF EXISTS ix_notification_unread")
    op.execute("DROP INDEX IF EXISTS ix_task_deadline")
    op.execute("DROP INDEX IF EXISTS ix_task_status")
    op.execute("DROP INDEX IF EXISTS ix_lead_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_lead_activity_created_at")
    op.execute("DROP INDEX IF EXISTS ix_lead_created_at")
    op.execute("DROP INDEX IF EXISTS ix_lead_next_action_date")
    op.execute("DROP INDEX IF EXISTS ix_lead_stage")
    op.execute("DROP INDEX IF EXISTS ix_opdracht_node_node_id")
    op.execute("DROP INDEX IF EXISTS ix_mattermost_link_code_person_id")
    op.execute("DROP INDEX IF EXISTS ix_tag_parent_id")
    op.execute("DROP INDEX IF EXISTS ix_parlementair_item_reviewed_by")
    op.execute("DROP INDEX IF EXISTS ix_suggested_edge_reviewed_by")
    op.execute("DROP INDEX IF EXISTS ix_suggested_edge_edge_type_id")
    op.execute("DROP INDEX IF EXISTS ix_suggested_edge_edge_id")
    op.execute("DROP INDEX IF EXISTS ix_access_request_reviewed_by_id")
    op.execute("DROP INDEX IF EXISTS ix_organisatie_eenheid_manager_id")
    op.execute("DROP INDEX IF EXISTS ix_organisatie_eenheid_parent_id")
    op.execute("DROP INDEX IF EXISTS ix_notification_related_task_id")
    op.execute("DROP INDEX IF EXISTS ix_notification_related_node_id")
    op.execute("DROP INDEX IF EXISTS ix_opdracht_verantwoordelijke_id")
    op.execute("DROP INDEX IF EXISTS ix_opdracht_opdrachtgever_id")
    op.execute("DROP INDEX IF EXISTS ix_opdracht_opdrachtnemer_id")
    op.execute("DROP INDEX IF EXISTS ix_lead_activity_author_id")
    op.execute("DROP INDEX IF EXISTS ix_lead_externe_organisatie_id")
    op.execute("DROP INDEX IF EXISTS ix_absence_substitute_id")
    op.execute("DROP INDEX IF EXISTS ix_absence_person_id")
