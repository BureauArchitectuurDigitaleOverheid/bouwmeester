"""add person_role composite indices

Composite indices for common person_role query patterns:
- (person_id, start_datum, eind_datum) for active roles per person (hot auth path)
- (organisatie_eenheid_id, role_id, eind_datum) for unit manager lookups
- (role_id, start_datum, eind_datum) for get_super_admins queries

Revision ID: a3f1e8c7d920
Revises: 88b0c7f2847a
Create Date: 2026-03-28 23:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f1e8c7d920"
down_revision: str | None = "88b0c7f2847a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Active roles per person (hot path: build_permission_context on every request)
    op.create_index(
        "ix_person_role_person_active",
        "person_role",
        ["person_id", "start_datum", "eind_datum"],
    )
    # Unit manager lookups by eenheid
    op.create_index(
        "ix_person_role_eenheid_role_active",
        "person_role",
        ["organisatie_eenheid_id", "role_id", "eind_datum"],
    )
    # Super admin lookups by role
    op.create_index(
        "ix_person_role_role_active",
        "person_role",
        ["role_id", "start_datum", "eind_datum"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_role_role_active", table_name="person_role")
    op.drop_index("ix_person_role_eenheid_role_active", table_name="person_role")
    op.drop_index("ix_person_role_person_active", table_name="person_role")
