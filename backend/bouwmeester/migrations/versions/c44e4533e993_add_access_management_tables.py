"""add access management tables

Revision ID: c44e4533e993
Revises: f920a0de4559
Create Date: 2026-03-28 14:36:11.922560

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c44e4533e993"
down_revision: str | None = "f920a0de4559"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# Role & permission seed data
# ---------------------------------------------------------------------------

ROLES = [
    (
        "super_admin",
        "Systeembeheerder",
        "Volledige toegang tot alle functionaliteit",
        "system",
        100,
    ),
    (
        "platform_admin",
        "Platformbeheerder",
        "Beheert whitelist, configuratie, audit en imports",
        "system",
        90,
    ),
    (
        "ministry_admin",
        "Ministeriebeheerder",
        "Beheert organisatie, gebruikers en rollen binnen een ministerie",
        "ministry",
        80,
    ),
    (
        "unit_manager",
        "Eenheidmanager",
        "Volledige toegang binnen een organisatie-eenheid",
        "unit",
        60,
    ),
    (
        "editor",
        "Bewerker",
        "Kan items aanmaken en bewerken binnen een organisatie-eenheid",
        "unit",
        40,
    ),
    (
        "viewer",
        "Lezer",
        "Alleen-lezen toegang binnen een organisatie-eenheid",
        "unit",
        20,
    ),
]

PERMISSIONS = [
    # node
    ("node:create", "node"),
    ("node:read", "node"),
    ("node:update", "node"),
    ("node:delete", "node"),
    # task
    ("task:create", "task"),
    ("task:read", "task"),
    ("task:update", "task"),
    ("task:delete", "task"),
    # edge
    ("edge:create", "edge"),
    ("edge:read", "edge"),
    ("edge:update", "edge"),
    ("edge:delete", "edge"),
    # lead
    ("lead:create", "lead"),
    ("lead:read", "lead"),
    ("lead:update", "lead"),
    ("lead:delete", "lead"),
    # initiatief
    ("initiatief:create", "initiatief"),
    ("initiatief:read", "initiatief"),
    ("initiatief:update", "initiatief"),
    ("initiatief:delete", "initiatief"),
    # opdracht
    ("opdracht:create", "opdracht"),
    ("opdracht:read", "opdracht"),
    ("opdracht:update", "opdracht"),
    ("opdracht:delete", "opdracht"),
    # org
    ("org:read", "org"),
    ("org:manage", "org"),
    # people
    ("people:read", "people"),
    ("people:manage", "people"),
    ("people:assign_role", "people"),
    # admin
    ("whitelist:manage", "admin"),
    ("audit:read", "admin"),
    ("config:manage", "admin"),
    ("feature_toggle:manage", "admin"),
    # import/export
    ("import_export:import", "import_export"),
    ("import_export:export", "import_export"),
    # tag
    ("tag:create", "tag"),
    ("tag:read", "tag"),
    ("tag:update", "tag"),
    ("tag:delete", "tag"),
    # resource_permission
    ("resource_permission:manage", "resource_permission"),
    # database
    ("database:backup", "database"),
    ("database:restore", "database"),
    ("database:reset", "database"),
]

# All permission IDs for convenience
_ALL_PERMS = [p[0] for p in PERMISSIONS]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": _ALL_PERMS,
    "platform_admin": [
        "whitelist:manage",
        "config:manage",
        "audit:read",
        "feature_toggle:manage",
        "import_export:import",
        "import_export:export",
        "database:backup",
        "database:restore",
        "database:reset",
        "people:read",
        "people:manage",
        "people:assign_role",
        "org:read",
    ],
    "ministry_admin": [
        "org:read",
        "org:manage",
        "people:read",
        "people:manage",
        "people:assign_role",
        "whitelist:manage",
        "feature_toggle:manage",
        "audit:read",
        "node:read",
        "task:read",
        "edge:read",
        "lead:read",
        "initiatief:read",
        "opdracht:read",
        "tag:read",
    ],
    "unit_manager": [
        "node:create",
        "node:read",
        "node:update",
        "node:delete",
        "task:create",
        "task:read",
        "task:update",
        "task:delete",
        "edge:create",
        "edge:read",
        "edge:update",
        "edge:delete",
        "lead:create",
        "lead:read",
        "lead:update",
        "lead:delete",
        "initiatief:create",
        "initiatief:read",
        "initiatief:update",
        "initiatief:delete",
        "opdracht:create",
        "opdracht:read",
        "opdracht:update",
        "opdracht:delete",
        "tag:create",
        "tag:read",
        "tag:update",
        "tag:delete",
        "resource_permission:manage",
        "people:read",
        "org:read",
    ],
    "editor": [
        "node:create",
        "node:read",
        "node:update",
        "task:create",
        "task:read",
        "task:update",
        "task:delete",
        "edge:create",
        "edge:read",
        "edge:update",
        "lead:create",
        "lead:read",
        "lead:update",
        "initiatief:create",
        "initiatief:read",
        "initiatief:update",
        "opdracht:create",
        "opdracht:read",
        "opdracht:update",
        "tag:create",
        "tag:read",
        "tag:update",
        "resource_permission:manage",
        "people:read",
        "org:read",
    ],
    "viewer": [
        "node:read",
        "task:read",
        "edge:read",
        "lead:read",
        "initiatief:read",
        "opdracht:read",
        "tag:read",
        "people:read",
        "org:read",
    ],
}


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Create tables
    # -----------------------------------------------------------------------

    op.create_table(
        "permission",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "role",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("naam", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.String(), nullable=False, comment="system|ministry|unit"),
        sa.Column(
            "rank", sa.Integer(), nullable=False, comment="Higher = more powerful"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("permission_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permission.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    op.create_table(
        "person_role",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column(
            "organisatie_eenheid_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("granted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_datum", sa.Date(), nullable=False),
        sa.Column("eind_datum", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"], ["organisatie_eenheid.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["granted_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id", "role_id", "organisatie_eenheid_id", name="uq_person_role"
        ),
        sa.CheckConstraint(
            "(role_id IN ('super_admin', 'platform_admin')"
            " AND organisatie_eenheid_id IS NULL)"
            " OR "
            "(role_id NOT IN ('super_admin', 'platform_admin')"
            " AND organisatie_eenheid_id IS NOT NULL)",
            name="ck_person_role_scope",
        ),
    )
    op.create_index("ix_person_role_person_id", "person_role", ["person_id"])
    op.create_index(
        "ix_person_role_organisatie_eenheid_id",
        "person_role",
        ["organisatie_eenheid_id"],
    )

    op.create_table(
        "resource_permission",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "resource_type",
            sa.String(),
            nullable=False,
            comment="corpus_node|initiatief|lead|team|opdracht",
        ),
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Polymorphic FK",
        ),
        sa.Column("rol", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id",
            "resource_type",
            "resource_id",
            "rol",
            name="uq_resource_permission",
        ),
    )
    op.create_index(
        "ix_resource_permission_person_id", "resource_permission", ["person_id"]
    )
    op.create_index(
        "ix_resource_permission_resource",
        "resource_permission",
        ["resource_type", "resource_id"],
    )

    op.create_table(
        "shared_access",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_eenheid_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_eenheid_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_level", sa.String(), nullable=False, comment="read|edit"),
        sa.Column("shared_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("geldig_van", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"], ["corpus_node.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_eenheid_id"], ["organisatie_eenheid.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_eenheid_id"], ["organisatie_eenheid.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["shared_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            """
            (source_node_id IS NOT NULL AND source_eenheid_id IS NULL)
            OR
            (source_node_id IS NULL AND source_eenheid_id IS NOT NULL)
            """,
            name="ck_shared_access_source",
        ),
    )
    op.create_index(
        "ix_shared_access_source_node_id", "shared_access", ["source_node_id"]
    )
    op.create_index(
        "ix_shared_access_source_eenheid_id", "shared_access", ["source_eenheid_id"]
    )
    op.create_index(
        "ix_shared_access_target_eenheid_id", "shared_access", ["target_eenheid_id"]
    )

    # -----------------------------------------------------------------------
    # 2. Seed reference data
    # -----------------------------------------------------------------------

    permission_table = sa.table("permission", sa.column("id"), sa.column("category"))
    op.bulk_insert(
        permission_table, [{"id": p[0], "category": p[1]} for p in PERMISSIONS]
    )

    role_table = sa.table(
        "role",
        sa.column("id"),
        sa.column("naam"),
        sa.column("description"),
        sa.column("level"),
        sa.column("rank"),
    )
    op.bulk_insert(
        role_table,
        [
            {"id": r[0], "naam": r[1], "description": r[2], "level": r[3], "rank": r[4]}
            for r in ROLES
        ],
    )

    role_perm_table = sa.table(
        "role_permission", sa.column("role_id"), sa.column("permission_id")
    )
    rows = []
    for role_id, perms in ROLE_PERMISSIONS.items():
        for perm_id in perms:
            rows.append({"role_id": role_id, "permission_id": perm_id})
    op.bulk_insert(role_perm_table, rows)

    # -----------------------------------------------------------------------
    # 3. Migrate existing data
    # -----------------------------------------------------------------------

    # 3a. is_admin=True -> person_role(super_admin)
    op.execute(
        sa.text("""
            INSERT INTO person_role (person_id, role_id, start_datum)
            SELECT id, 'super_admin', CURRENT_DATE
            FROM person
            WHERE is_admin = TRUE
            ON CONFLICT DO NOTHING
        """)
    )

    # 3b. Active PersonOrganisatieEenheid -> person_role(editor)
    op.execute(
        sa.text("""
        INSERT INTO person_role (
            person_id, role_id,
            organisatie_eenheid_id, start_datum, eind_datum
        )
        SELECT person_id, 'editor',
            organisatie_eenheid_id, start_datum, eind_datum
        FROM person_organisatie_eenheid
        ON CONFLICT DO NOTHING
    """)
    )

    # 3c. NodeStakeholder -> resource_permission
    _migrate_to_rp = """
        INSERT INTO resource_permission (
            person_id, resource_type,
            resource_id, rol, created_at
        )
        SELECT person_id, '{rtype}', {col}, rol, {ts}
        FROM {src}
        ON CONFLICT DO NOTHING
    """

    op.execute(
        sa.text(
            _migrate_to_rp.format(
                rtype="corpus_node",
                col="node_id",
                ts="created_at",
                src="node_stakeholder",
            )
        )
    )

    # 3d. InitiatiefMember -> resource_permission
    op.execute(
        sa.text(
            _migrate_to_rp.format(
                rtype="initiatief",
                col="initiatief_id",
                ts="created_at",
                src="initiatief_member",
            )
        )
    )

    # 3e. LeadContact -> resource_permission
    op.execute(
        sa.text(
            _migrate_to_rp.format(
                rtype="lead",
                col="lead_id",
                ts="created_at",
                src="lead_contact",
            )
        )
    )

    # 3f. TeamMember -> resource_permission
    op.execute(
        sa.text(
            _migrate_to_rp.format(
                rtype="team",
                col="team_id",
                ts="NOW()",
                src="team_member",
            )
        )
    )


def downgrade() -> None:
    op.drop_table("shared_access")
    op.drop_table("resource_permission")
    op.drop_table("person_role")
    op.drop_table("role_permission")
    op.drop_table("role")
    op.drop_table("permission")
