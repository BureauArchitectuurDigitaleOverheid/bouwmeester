"""merge temporal org and parlementair branches

Revision ID: 4a36da453fd2
Revises: 95d48f56f750, f01b49dfb7ef
Create Date: 2026-02-09 10:10:54.941641

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a36da453fd2'
down_revision: Union[str, None] = ('95d48f56f750', 'f01b49dfb7ef')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
