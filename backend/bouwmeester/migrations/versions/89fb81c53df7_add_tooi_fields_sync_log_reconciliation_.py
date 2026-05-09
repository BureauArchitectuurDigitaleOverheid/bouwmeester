"""add tooi fields, sync log, reconciliation, email_domein

Revision ID: 89fb81c53df7
Revises: da41cdbe6d18
Create Date: 2026-05-09 07:49:02.971914
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "89fb81c53df7"
down_revision: str | None = "da41cdbe6d18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # OrganisatieEenheid: nieuwe kolommen voor TOOI-integratie en externe-org velden
    op.add_column(
        "organisatie_eenheid",
        sa.Column("afkorting", sa.String(), nullable=True),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column("website", sa.String(), nullable=True),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column("kvk_nummer", sa.String(), nullable=True),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column("tooi_uri", sa.String(), nullable=True),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column("tooi_organisatiesoort", sa.String(), nullable=True),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column("oin", sa.String(), nullable=True),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column("fte_aantal", sa.Integer(), nullable=True),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column(
            "bron",
            sa.String(),
            server_default=sa.text("'handmatig'"),
            nullable=False,
            comment=("handmatig | tooi | synthetisch | organogram_scrape | fcc_import"),
        ),
    )
    op.create_index(
        op.f("ix_organisatie_eenheid_tooi_uri"),
        "organisatie_eenheid",
        ["tooi_uri"],
        unique=True,
    )

    # Person: TK OData identifier + bron
    op.add_column(
        "person",
        sa.Column(
            "tk_persoon_id",
            sa.String(),
            nullable=True,
            comment="UUID van TK Open Data Persoon-entity",
        ),
    )
    op.add_column(
        "person",
        sa.Column(
            "bron",
            sa.String(),
            server_default=sa.text("'handmatig'"),
            nullable=False,
            comment="handmatig | tk_odata | roo_leidinggevende | kabinet_yaml",
        ),
    )
    op.create_index(
        op.f("ix_person_tk_persoon_id"),
        "person",
        ["tk_persoon_id"],
        unique=True,
    )

    # PersonOrganisatieEenheid: functietitel + bron
    op.add_column(
        "person_organisatie_eenheid",
        sa.Column(
            "functietitel",
            sa.String(),
            nullable=True,
            comment="Bv. 'Tweede Kamerlid', 'Minister', 'SG', 'directeur'",
        ),
    )
    op.add_column(
        "person_organisatie_eenheid",
        sa.Column(
            "bron",
            sa.String(),
            server_default=sa.text("'handmatig'"),
            nullable=False,
            comment="handmatig | tk_odata | kabinet_yaml | roo_leidinggevende",
        ),
    )

    # OrganisatieEmailDomein
    op.create_table(
        "organisatie_email_domein",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=False),
        sa.Column("domein", sa.String(), nullable=False),
        sa.Column(
            "bron",
            sa.String(),
            server_default=sa.text("'rio'"),
            nullable=False,
            comment="rio | handmatig",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"],
            ["organisatie_eenheid.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domein", name="uq_organisatie_email_domein_domein"),
    )
    op.create_index(
        op.f("ix_organisatie_email_domein_domein"),
        "organisatie_email_domein",
        ["domein"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organisatie_email_domein_organisatie_eenheid_id"),
        "organisatie_email_domein",
        ["organisatie_eenheid_id"],
        unique=False,
    )

    # TooiSyncLog
    op.create_table(
        "tooi_sync_log",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "sync_run_id",
            sa.UUID(),
            nullable=False,
            comment="Gegroepeerd per sync-run zodat je een hele run kan terugdraaien",
        ),
        sa.Column(
            "bron",
            sa.String(),
            nullable=False,
            comment=(
                "tooi | rio | ministeries_csv | organogram | tk_odata | kabinet | "
                "roo_leidinggevenden"
            ),
        ),
        sa.Column(
            "action",
            sa.String(),
            nullable=False,
            comment="add | rename | move | soft_delete | enrich | conflict",
        ),
        sa.Column("tooi_uri", sa.String(), nullable=True),
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=True),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "after",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tooi_sync_log_created_at"),
        "tooi_sync_log",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tooi_sync_log_organisatie_eenheid_id"),
        "tooi_sync_log",
        ["organisatie_eenheid_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tooi_sync_log_person_id"),
        "tooi_sync_log",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tooi_sync_log_sync_run_id"),
        "tooi_sync_log",
        ["sync_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tooi_sync_log_tooi_uri"),
        "tooi_sync_log",
        ["tooi_uri"],
        unique=False,
    )

    # PendingReconciliation
    op.create_table(
        "pending_reconciliation",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "resource_type",
            sa.String(),
            nullable=False,
            comment="organisatie_eenheid | person",
        ),
        sa.Column(
            "handmatige_id",
            sa.UUID(),
            nullable=False,
            comment="ID van de bestaande handmatige rij",
        ),
        sa.Column(
            "kandidaat_id",
            sa.UUID(),
            nullable=True,
            comment=("ID van de TOOI/sync-rij die als duplicate-kandidaat is gevonden"),
        ),
        sa.Column(
            "kandidaat_bron",
            sa.String(),
            nullable=False,
            comment="tooi | tk_odata | kabinet | organogram_scrape",
        ),
        sa.Column(
            "match_reden",
            sa.String(),
            nullable=False,
            comment=(
                "naam_exact | naam_normalized | afkorting | tk_persoon_id_match | etc."
            ),
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'open'"),
            nullable=False,
            comment="open | merged | ignored",
        ),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["resolved_by"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pending_reconciliation_created_at"),
        "pending_reconciliation",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pending_reconciliation_handmatige_id"),
        "pending_reconciliation",
        ["handmatige_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pending_reconciliation_kandidaat_id"),
        "pending_reconciliation",
        ["kandidaat_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pending_reconciliation_resolved_by"),
        "pending_reconciliation",
        ["resolved_by"],
        unique=False,
    )

    # Seed synthetische top-level groepen — TOOI/scrape-syncs hebben deze
    # nodig als parent-target voor gemeenten, provincies, marktpartijen, etc.
    # Idempotent: skip als rij met dezelfde naam al bestaat (NOT EXISTS).
    namen = [
        (
            "Hoge Colleges van Staat",
            "Grondwettelijke instellingen die naast de regering staan.",
        ),
        ("Rechtspraak", "Onafhankelijke rechtsprekende macht."),
        ("Openbaar Ministerie", "Het Openbaar Ministerie en arrondissementsparketten."),
        ("Gemeenten", "Alle Nederlandse gemeenten."),
        ("Provincies", "De twaalf provincies."),
        ("Waterschappen", "Waterschappen en hoogheemraadschappen."),
        ("Samenwerkingsorganisaties", "Gemeenschappelijke regelingen e.d."),
        (
            "Caribische openbare lichamen",
            "Bonaire, Sint Eustatius en Saba (BES-eilanden).",
        ),
        ("ZBO's en agentschappen", "Vangnet voor ZBO's en agentschappen."),
        ("Marktpartijen en overige", "Marktpartijen, stichtingen, koepelorganisaties."),
        (
            "Internationale organisaties",
            "EU-instellingen, VN-organen, OECD, NAVO en andere internationale "
            "organen waar NL-stakeholders mee samenwerken.",
        ),
        (
            "Onderwijsinstellingen",
            "Universiteiten, hogescholen, mbo-instellingen. Niet in TOOI maar "
            "vaak gekoppeld aan beleidsdossiers.",
        ),
    ]
    for naam, beschrijving in namen:
        op.execute(
            sa.text(
                """
                INSERT INTO organisatie_eenheid (naam, type, bron, beschrijving)
                SELECT :naam, 'synthetische_groep', 'synthetisch', :beschrijving
                WHERE NOT EXISTS (
                    SELECT 1 FROM organisatie_eenheid
                    WHERE bron='synthetisch' AND naam = :naam
                )
                """
            ).bindparams(naam=naam, beschrijving=beschrijving)
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_pending_reconciliation_resolved_by"),
        table_name="pending_reconciliation",
    )
    op.drop_index(
        op.f("ix_pending_reconciliation_kandidaat_id"),
        table_name="pending_reconciliation",
    )
    op.drop_index(
        op.f("ix_pending_reconciliation_handmatige_id"),
        table_name="pending_reconciliation",
    )
    op.drop_index(
        op.f("ix_pending_reconciliation_created_at"),
        table_name="pending_reconciliation",
    )
    op.drop_table("pending_reconciliation")

    op.drop_index(op.f("ix_tooi_sync_log_tooi_uri"), table_name="tooi_sync_log")
    op.drop_index(op.f("ix_tooi_sync_log_sync_run_id"), table_name="tooi_sync_log")
    op.drop_index(op.f("ix_tooi_sync_log_person_id"), table_name="tooi_sync_log")
    op.drop_index(
        op.f("ix_tooi_sync_log_organisatie_eenheid_id"), table_name="tooi_sync_log"
    )
    op.drop_index(op.f("ix_tooi_sync_log_created_at"), table_name="tooi_sync_log")
    op.drop_table("tooi_sync_log")

    op.drop_index(
        op.f("ix_organisatie_email_domein_organisatie_eenheid_id"),
        table_name="organisatie_email_domein",
    )
    op.drop_index(
        op.f("ix_organisatie_email_domein_domein"),
        table_name="organisatie_email_domein",
    )
    op.drop_table("organisatie_email_domein")

    op.drop_column("person_organisatie_eenheid", "bron")
    op.drop_column("person_organisatie_eenheid", "functietitel")

    op.drop_index(op.f("ix_person_tk_persoon_id"), table_name="person")
    op.drop_column("person", "bron")
    op.drop_column("person", "tk_persoon_id")

    op.drop_index(
        op.f("ix_organisatie_eenheid_tooi_uri"), table_name="organisatie_eenheid"
    )
    op.drop_column("organisatie_eenheid", "bron")
    op.drop_column("organisatie_eenheid", "fte_aantal")
    op.drop_column("organisatie_eenheid", "oin")
    op.drop_column("organisatie_eenheid", "tooi_organisatiesoort")
    op.drop_column("organisatie_eenheid", "tooi_uri")
    op.drop_column("organisatie_eenheid", "kvk_nummer")
    op.drop_column("organisatie_eenheid", "website")
    op.drop_column("organisatie_eenheid", "afkorting")
