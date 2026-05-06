"""add missing indexes recent tables

Revision ID: 1fe90cecedd9
Revises: 2c4d6e8f9a01
Create Date: 2026-05-06 12:00:00.000000

Sluit de FK- en hot-filter-index gaten die door recente migraties zijn
ontstaan (stakeholder_assessment, initiatief_update, samenwerkingsverband,
notification.related_lead_id, lead.engagement_type). Idempotent via
``if_not_exists=True`` in dezelfde stijl als 025becdecf77.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1fe90cecedd9"
down_revision: str | None = "2c4d6e8f9a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: list[tuple[str, str, list[str]]] = [
    # FK columns added in recent migrations that skipped the FK index.
    ("ix_notification_related_lead_id", "notification", ["related_lead_id"]),
    (
        "ix_stakeholder_assessment_assessed_by_id",
        "stakeholder_assessment",
        ["assessed_by_id"],
    ),
    (
        "ix_initiatief_update_published_by_id",
        "initiatief_update",
        ["published_by_id"],
    ),
    ("ix_initiatief_created_by_id", "initiatief", ["created_by_id"]),
    (
        "ix_samenwerkingsverband_created_by_id",
        "samenwerkingsverband",
        ["created_by_id"],
    ),
    # Hot filter columns.
    ("ix_samenwerkingsverband_type", "samenwerkingsverband", ["type"]),
    ("ix_lead_engagement_type", "lead", ["engagement_type"]),
    # Composite for stakeholder_assessment.list_for_scope (scope_type+scope_id).
    (
        "ix_stakeholder_assessment_scope",
        "stakeholder_assessment",
        ["scope_type", "scope_id"],
    ),
]


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)
    # Drop redundant single-column index now that the composite
    # (scope_type, scope_id) handles every scope_id lookup we make.
    op.drop_index(
        "ix_stakeholder_assessment_scope_id",
        table_name="stakeholder_assessment",
        if_exists=True,
    )


def downgrade() -> None:
    op.create_index(
        "ix_stakeholder_assessment_scope_id",
        "stakeholder_assessment",
        ["scope_id"],
        if_not_exists=True,
    )
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
