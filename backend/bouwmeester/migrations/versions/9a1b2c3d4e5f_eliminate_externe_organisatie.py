"""eliminate externe_organisatie, FK-rewrite naar organisatie_eenheid

Past `scripts/data/externe_org_reconciliation.yaml` toe:
  - merge_tooi  -> bestaande TOOI-rij wordt FK-target
  - nieuw_handmatig -> nieuwe organisatie_eenheid rij onder synthetische groep

Daarna FK-rewrite op lead.externe_organisatie_id en opdracht.opdrachtnemer_id
naar nieuwe kolommen. Tot slot tabel `externe_organisatie` droppen.

Voor onbekende ExterneOrganisatie-rijen (niet in YAML): default = nieuwe
organisatie_eenheid onder 'Marktpartijen en overige' met type op basis van
ExterneOrganisatie.type.

Revision ID: 9a1b2c3d4e5f
Revises: 89fb81c53df7
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
import yaml
from alembic import op

revision: str = "9a1b2c3d4e5f"
down_revision: str | None = "89fb81c53df7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _load_reconciliation() -> dict[str, dict]:
    """Lees scripts/data/externe_org_reconciliation.yaml uit het backend-pad."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent
        / "scripts"
        / "data"
        / "externe_org_reconciliation.yaml",
        Path("backend/scripts/data/externe_org_reconciliation.yaml"),
        Path("scripts/data/externe_org_reconciliation.yaml"),
    ]
    for p in candidates:
        if p.exists():
            data = yaml.safe_load(p.read_text()) or {}
            return data.get("reconciliations") or {}
    raise FileNotFoundError(
        "externe_org_reconciliation.yaml niet gevonden — verwacht in "
        "backend/scripts/data/."
    )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Voeg nieuwe kolommen toe op lead/opdracht (nullable, FK naar organisatie_eenheid)  # noqa: E501
    op.add_column(
        "lead",
        sa.Column(
            "organisatie_eenheid_id",
            sa.UUID(),
            sa.ForeignKey("organisatie_eenheid.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "opdracht",
        sa.Column(
            "opdrachtnemer_eenheid_id",
            sa.UUID(),
            sa.ForeignKey("organisatie_eenheid.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. Bouw mapping externe_organisatie.id -> organisatie_eenheid.id
    rec_map = _load_reconciliation()

    externe_rows = bind.execute(
        sa.text(
            "SELECT id, naam, afkorting, type, kvk_nummer, website, beschrijving "
            "FROM externe_organisatie"
        )
    ).fetchall()

    # Cache: synthetische groepen
    synth_rows = bind.execute(
        sa.text("SELECT id, naam FROM organisatie_eenheid WHERE bron='synthetisch'")
    ).fetchall()
    synth_by_naam = {r.naam: r.id for r in synth_rows}

    mapping: dict[str, str] = {}  # externe_org_id (str) -> organisatie_eenheid_id (str)

    def vind_tooi_target(entry: dict) -> str | None:
        match = entry.get("match")
        if match == "naam_exact":
            row = bind.execute(
                sa.text(
                    "SELECT id FROM organisatie_eenheid "
                    "WHERE bron='tooi' AND naam = :n LIMIT 1"
                ),
                {"n": entry["naam"]},
            ).fetchone()
        elif match == "afkorting":
            afk = entry["afkorting_voor_match"]
            row = bind.execute(
                sa.text(
                    "SELECT id FROM organisatie_eenheid "
                    "WHERE bron='tooi' AND lower(afkorting) = lower(:a) LIMIT 1"
                ),
                {"a": afk},
            ).fetchone()
            if row is None and "fallback_naam_search" in entry:
                row = bind.execute(
                    sa.text(
                        "SELECT id FROM organisatie_eenheid "
                        "WHERE bron='tooi' AND naam ILIKE :s LIMIT 1"
                    ),
                    {"s": f"%{entry['fallback_naam_search']}%"},
                ).fetchone()
        elif match == "tooi_uri":
            row = bind.execute(
                sa.text(
                    "SELECT id FROM organisatie_eenheid "
                    "WHERE bron='tooi' AND naam = :n LIMIT 1"
                ),
                {"n": entry["tooi_uri_search_naam"]},
            ).fetchone()
        else:
            return None
        return str(row.id) if row else None

    for ext in externe_rows:
        entry = rec_map.get(ext.naam)
        target_id: str | None = None

        if entry is not None:
            actie = entry.get("actie")
            if actie == "merge_tooi":
                target_id = vind_tooi_target(entry)
                if target_id is None:
                    # Fallback: maak handmatig aan onder Marktpartijen
                    actie = "nieuw_handmatig"
                    entry = {
                        "actie": "nieuw_handmatig",
                        "type": ext.type,
                        "parent_synth": "Marktpartijen en overige",
                    }

            if actie == "nieuw_handmatig":
                synth_id = synth_by_naam.get(
                    entry.get("parent_synth", "Marktpartijen en overige")
                )
                row = bind.execute(
                    sa.text(
                        "INSERT INTO organisatie_eenheid "
                        "(naam, type, parent_id, bron, afkorting, kvk_nummer, "
                        "website, beschrijving) "
                        "VALUES (:n, :t, :p, 'handmatig', :a, :k, :w, :b) "
                        "RETURNING id"
                    ),
                    {
                        "n": ext.naam,
                        "t": entry.get("type", ext.type),
                        "p": synth_id,
                        "a": ext.afkorting,
                        "k": ext.kvk_nummer,
                        "w": ext.website,
                        "b": ext.beschrijving,
                    },
                ).fetchone()
                target_id = str(row.id)
        else:
            # Geen YAML-entry: default fallback onder Marktpartijen
            synth_id = synth_by_naam.get("Marktpartijen en overige")
            row = bind.execute(
                sa.text(
                    "INSERT INTO organisatie_eenheid "
                    "(naam, type, parent_id, bron, afkorting, kvk_nummer, "
                    "website, beschrijving) "
                    "VALUES (:n, :t, :p, 'fcc_import', :a, :k, :w, :b) "
                    "RETURNING id"
                ),
                {
                    "n": ext.naam,
                    "t": ext.type or "overig",
                    "p": synth_id,
                    "a": ext.afkorting,
                    "k": ext.kvk_nummer,
                    "w": ext.website,
                    "b": ext.beschrijving,
                },
            ).fetchone()
            target_id = str(row.id)

        if target_id is not None:
            mapping[str(ext.id)] = target_id

    # 3. FK-rewrite voor lead en opdracht
    for ext_id, org_id in mapping.items():
        bind.execute(
            sa.text(
                "UPDATE lead SET organisatie_eenheid_id = :o "
                "WHERE externe_organisatie_id = :e"
            ),
            {"o": org_id, "e": ext_id},
        )
        bind.execute(
            sa.text(
                "UPDATE opdracht SET opdrachtnemer_eenheid_id = :o "
                "WHERE opdrachtnemer_id = :e"
            ),
            {"o": org_id, "e": ext_id},
        )

    # 4. Drop oude FK-kolommen
    op.drop_column("lead", "externe_organisatie_id")
    op.drop_column("opdracht", "opdrachtnemer_id")

    # 5. Drop tabel externe_organisatie
    op.drop_table("externe_organisatie")


def downgrade() -> None:
    # Een echte downgrade vereist het terug-vinden van de externe_org-rijen,
    # wat lossy is omdat de kvk/website/beschrijving al zijn verplaatst. We
    # bouwen alleen de structuur terug zodat een schone re-run kan plaatsvinden.
    op.create_table(
        "externe_organisatie",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("naam", sa.String(), nullable=False),
        sa.Column("afkorting", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("kvk_nummer", sa.String(), nullable=True),
        sa.Column("website", sa.String(), nullable=True),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type IN ('uitvoeringsorganisatie', 'zbo', 'koepelorganisatie', "
            "'stichting', 'marktpartij', 'overig')",
            name="ck_externe_organisatie_type",
        ),
        sa.UniqueConstraint("naam", name="uq_externe_organisatie_naam"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "lead",
        sa.Column(
            "externe_organisatie_id",
            sa.UUID(),
            sa.ForeignKey("externe_organisatie.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "opdracht",
        sa.Column(
            "opdrachtnemer_id",
            sa.UUID(),
            sa.ForeignKey("externe_organisatie.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_column("lead", "organisatie_eenheid_id")
    op.drop_column("opdracht", "opdrachtnemer_eenheid_id")
