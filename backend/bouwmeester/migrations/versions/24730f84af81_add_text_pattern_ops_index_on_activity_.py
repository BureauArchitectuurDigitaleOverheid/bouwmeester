"""add text_pattern_ops index on activity event_type

Revision ID: 24730f84af81
Revises: 492a105cdce5
Create Date: 2026-02-10 21:32:55.346251

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "24730f84af81"
down_revision: Union[str, None] = "492a105cdce5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_activity_event_type_pattern",
        "activity",
        ["event_type"],
        unique=False,
        postgresql_ops={"event_type": "text_pattern_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_activity_event_type_pattern",
        table_name="activity",
        postgresql_ops={"event_type": "text_pattern_ops"},
    )
