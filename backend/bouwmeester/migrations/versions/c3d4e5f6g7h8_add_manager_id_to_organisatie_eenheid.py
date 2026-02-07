"""add manager_id to organisatie_eenheid

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-02-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'organisatie_eenheid',
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('person.id', ondelete='SET NULL'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('organisatie_eenheid', 'manager_id')
