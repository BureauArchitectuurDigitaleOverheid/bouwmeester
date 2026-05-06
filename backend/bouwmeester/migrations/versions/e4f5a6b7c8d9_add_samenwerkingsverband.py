"""add samenwerkingsverband and persoon_samenwerkingsverband

Revision ID: e4f5a6b7c8d9
Revises: d2e3f4a5b6c7
Create Date: 2026-05-06 16:00:00.000000

Voegt het Samenwerkingsverband-domein toe: ad-hoc samenwerkingsvormen
(programma, werkgroep, opschalingsticket, ketenproject) los van de
hierarchische OrganisatieEenheid-boom, met persoon-lidmaatschap via een
junction-tabel.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_PERMISSIONS = [
    ("samenwerkingsverband:create", "samenwerkingsverband"),
    ("samenwerkingsverband:read", "samenwerkingsverband"),
    ("samenwerkingsverband:update", "samenwerkingsverband"),
    ("samenwerkingsverband:delete", "samenwerkingsverband"),
]

# Zelfde rolset als initiatief: super_admin/ministry_admin/unit_manager
# krijgen alles, editor mag create/read/update (niet delete), viewer alleen
# read. platform_admin is bewust infra-only.
_ROLE_GRANTS: dict[str, list[str]] = {
    "super_admin": [p[0] for p in _NEW_PERMISSIONS],
    "ministry_admin": [p[0] for p in _NEW_PERMISSIONS],
    "unit_manager": [p[0] for p in _NEW_PERMISSIONS],
    "editor": [
        "samenwerkingsverband:create",
        "samenwerkingsverband:read",
        "samenwerkingsverband:update",
    ],
    "viewer": ["samenwerkingsverband:read"],
}


def upgrade() -> None:
    op.create_table(
        "samenwerkingsverband",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("naam", sa.String(), nullable=False),
        sa.Column(
            "type",
            sa.String(),
            nullable=False,
            comment="programma|werkgroep|opschalingsticket|ketenproject",
        ),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column("start_datum", sa.Date(), nullable=True),
        sa.Column("eind_datum", sa.Date(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "persoon_samenwerkingsverband",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "samenwerkingsverband_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("rol", sa.String(), nullable=True),
        sa.Column("start_datum", sa.Date(), nullable=False),
        sa.Column("eind_datum", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["samenwerkingsverband_id"],
            ["samenwerkingsverband.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id",
            "samenwerkingsverband_id",
            "start_datum",
            name="uq_persoon_samenwerkingsverband_lidmaatschap",
        ),
    )
    op.create_index(
        op.f("ix_persoon_samenwerkingsverband_person_id"),
        "persoon_samenwerkingsverband",
        ["person_id"],
    )
    op.create_index(
        op.f("ix_persoon_samenwerkingsverband_samenwerkingsverband_id"),
        "persoon_samenwerkingsverband",
        ["samenwerkingsverband_id"],
    )

    permission_table = sa.table(
        "permission",
        sa.column("id", sa.String()),
        sa.column("category", sa.String()),
    )
    op.bulk_insert(
        permission_table,
        [{"id": pid, "category": cat} for pid, cat in _NEW_PERMISSIONS],
    )

    role_permission_table = sa.table(
        "role_permission",
        sa.column("role_id", sa.String()),
        sa.column("permission_id", sa.String()),
    )
    op.bulk_insert(
        role_permission_table,
        [
            {"role_id": role_id, "permission_id": perm_id}
            for role_id, perms in _ROLE_GRANTS.items()
            for perm_id in perms
        ],
    )


def downgrade() -> None:
    perm_ids = [p[0] for p in _NEW_PERMISSIONS]
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM role_permission WHERE permission_id = ANY(:ids)"),
        {"ids": perm_ids},
    )
    bind.execute(
        sa.text("DELETE FROM permission WHERE id = ANY(:ids)"),
        {"ids": perm_ids},
    )

    op.drop_index(
        op.f("ix_persoon_samenwerkingsverband_samenwerkingsverband_id"),
        table_name="persoon_samenwerkingsverband",
    )
    op.drop_index(
        op.f("ix_persoon_samenwerkingsverband_person_id"),
        table_name="persoon_samenwerkingsverband",
    )
    op.drop_table("persoon_samenwerkingsverband")
    op.drop_table("samenwerkingsverband")
