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
    op.create_unique_constraint("uq_person_api_key_hash", "person", ["api_key_hash"])

    # Migrate existing plaintext api_key values to hashed form.
    # PostgreSQL sha256(text::bytea) and Python hashlib.sha256(text.encode("utf-8"))
    # produce identical digests for ASCII-only strings (which all bm_<hex> keys are).
    op.execute(
        """
        UPDATE person
        SET api_key_hash = encode(sha256(api_key::bytea), 'hex'),
            api_key = NULL
        WHERE api_key IS NOT NULL
        """
    )

    # Drop the legacy plaintext column — all keys are now stored as hashes.
    op.drop_column("person", "api_key")

    # Prevent duplicate agent names at the DB level (application-level check alone
    # is vulnerable to race conditions).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_person_agent_naam
        ON person (naam)
        WHERE is_agent = true AND is_active = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_person_agent_naam")
    op.add_column("person", sa.Column("api_key", sa.String(), nullable=True))
    op.drop_constraint("uq_person_api_key_hash", "person", type_="unique")
    op.drop_column("person", "api_key_hash")
