"""add organisatie_eenheid and person FK

Revision ID: a1b2c3d4e5f6
Revises: 2ebdc49f0f07
Create Date: 2026-02-07 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '2ebdc49f0f07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('organisatie_eenheid',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('naam', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False, comment='e.g. ministerie|directoraat_generaal|directie|afdeling|team'),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('beschrijving', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['organisatie_eenheid.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.add_column('person', sa.Column('organisatie_eenheid_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_person_organisatie_eenheid',
        'person', 'organisatie_eenheid',
        ['organisatie_eenheid_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_person_organisatie_eenheid', 'person', type_='foreignkey')
    op.drop_column('person', 'organisatie_eenheid_id')
    op.drop_table('organisatie_eenheid')
