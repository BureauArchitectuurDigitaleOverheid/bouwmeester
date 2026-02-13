"""add api_key_hash to person

Revision ID: a7f3b2c1d4e5
Revises: a7f3b2c1d9e8
Create Date: 2026-02-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f3b2c1d4e5"
down_revision: str | None = "a7f3b2c1d9e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("person", sa.Column("api_key_hash", sa.String(), nullable=True))
    op.create_index("ix_person_api_key_hash", "person", ["api_key_hash"])

    # Migrate existing plaintext api_key values to hashed form.
    # Uses PostgreSQL's built-in encode(digest(...)) (pgcrypto not needed for sha256).
    op.execute(
        """
        UPDATE person
        SET api_key_hash = encode(sha256(api_key::bytea), 'hex'),
            api_key = NULL
        WHERE api_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_person_api_key_hash", table_name="person")
    op.drop_column("person", "api_key_hash")
