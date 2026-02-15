"""add mattermost user mapping

Revision ID: ff993f2c1770
Revises: 1cbc1f263552
Create Date: 2026-02-15 14:45:47.558733

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff993f2c1770'
down_revision: Union[str, None] = '1cbc1f263552'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('mattermost_user',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('person_id', sa.UUID(), nullable=False),
    sa.Column('mattermost_user_id', sa.String(length=26), nullable=False),
    sa.Column('mattermost_username', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['person_id'], ['person.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('mattermost_user_id'),
    sa.UniqueConstraint('person_id')
    )
    op.create_table('mattermost_link_code',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('person_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['person_id'], ['person.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )


def downgrade() -> None:
    op.drop_table('mattermost_link_code')
    op.drop_table('mattermost_user')
