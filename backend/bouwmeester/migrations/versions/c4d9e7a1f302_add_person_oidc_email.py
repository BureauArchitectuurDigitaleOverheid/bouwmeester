"""Add person.oidc_email and make emails unique regardless of case

``person.oidc_email`` holds the email claim of the most recent OIDC login.
WebAuthn logins and the admin seed trust it instead of the editable
``person.email``.  It is left empty and fills itself on each person's next
SSO login: copying it from an address anyone could edit before this change
would trust exactly what it is meant to replace.

Emails are stored lower-case from now on and ``person_email`` gets a unique
index on ``lower(email)``, so two people can no longer hold the same address
in a different case.

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

    # Fails (and rolls back) if two rows differ only in case; resolve those
    # by hand first.  Production had none on 2026-09-26.
    op.execute("UPDATE person_email SET email = lower(trim(email))")
    op.create_index(
        "uq_person_email_lower",
        "person_email",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_person_email_lower", table_name="person_email")
    op.drop_column("person", "oidc_email")
