"""Add person.oidc_email

The email claim of the most recent OIDC login.  WebAuthn logins check the
whitelist against this column instead of the editable ``person.email``.

Revision ID: c4d9e7a1f302
Revises: b8c3e21d75f4
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d9e7a1f302"
down_revision = "b8c3e21d75f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("person", sa.Column("oidc_email", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("person", "oidc_email")
