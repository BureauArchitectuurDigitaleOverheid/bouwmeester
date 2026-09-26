"""Rename the default WebAuthn label from "Biometrie" to "Passkey"

A passkey is not necessarily biometric (a pin or a security key works too),
so the UI calls it a passkey now. Existing credentials still carry the old
default label; only that exact default is renamed.

Revision ID: d1a6f3b8c925
Revises: c4d9e7a1f302
Create Date: 2026-09-26
"""

from alembic import op

revision = "d1a6f3b8c925"
down_revision = "c4d9e7a1f302"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE webauthn_credential SET label = 'Passkey' WHERE label = 'Biometrie'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE webauthn_credential SET label = 'Biometrie' WHERE label = 'Passkey'"
    )
