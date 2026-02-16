"""seed default edge schema rules

Revision ID: 1cbc1f263552
Revises: 7ad2814283b1
Create Date: 2026-02-15 11:59:35.766542

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1cbc1f263552"
down_revision: str | None = "7ad2814283b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All node types in the system
ALL_NODE_TYPES = [
    "dossier",
    "doel",
    "instrument",
    "beleidskader",
    "maatregel",
    "politieke_input",
    "probleem",
    "effect",
    "beleidsoptie",
    "bron",
    "notitie",
    "overig",
]


def _build_rules() -> list[tuple[str, str, str]]:
    """Build the default edge schema rules based on beleidstheorie /
    ArchiMate Motivation patterns."""
    rules: list[tuple[str, str, str]] = []

    # --- Core beleidstheorie / ArchiMate Motivation patterns ---

    # probleem
    rules.append(("probleem", "doel", "leidt_tot"))
    rules.append(("probleem", "probleem", "leidt_tot"))
    rules.append(("probleem", "probleem", "onderdeel_van"))

    # doel
    rules.append(("doel", "doel", "draagt_bij_aan"))
    rules.append(("doel", "doel", "onderdeel_van"))
    rules.append(("doel", "doel", "conflicteert_met"))

    # instrument
    rules.append(("instrument", "doel", "implementeert"))
    rules.append(("instrument", "doel", "draagt_bij_aan"))
    rules.append(("instrument", "probleem", "adresseert"))
    rules.append(("instrument", "instrument", "onderdeel_van"))
    rules.append(("instrument", "instrument", "conflicteert_met"))
    rules.append(("instrument", "instrument", "vervangt"))
    rules.append(("instrument", "instrument", "vloeit_voort_uit"))

    # maatregel
    rules.append(("maatregel", "doel", "implementeert"))
    rules.append(("maatregel", "doel", "draagt_bij_aan"))
    rules.append(("maatregel", "probleem", "adresseert"))
    rules.append(("maatregel", "effect", "leidt_tot"))
    rules.append(("maatregel", "maatregel", "onderdeel_van"))
    rules.append(("maatregel", "maatregel", "conflicteert_met"))
    rules.append(("maatregel", "maatregel", "vervangt"))
    rules.append(("maatregel", "maatregel", "vloeit_voort_uit"))
    rules.append(("maatregel", "instrument", "implementeert"))

    # effect
    rules.append(("effect", "doel", "meet"))
    rules.append(("effect", "doel", "draagt_bij_aan"))
    rules.append(("effect", "effect", "leidt_tot"))
    rules.append(("effect", "effect", "onderdeel_van"))

    # beleidskader
    rules.append(("beleidskader", "doel", "draagt_bij_aan"))
    rules.append(("beleidskader", "beleidskader", "onderdeel_van"))
    rules.append(("beleidskader", "beleidskader", "vervangt"))
    rules.append(("beleidskader", "beleidskader", "vloeit_voort_uit"))
    rules.append(("beleidskader", "instrument", "vereist"))
    rules.append(("beleidskader", "maatregel", "vereist"))

    # beleidsoptie
    rules.append(("beleidsoptie", "doel", "draagt_bij_aan"))
    rules.append(("beleidsoptie", "probleem", "adresseert"))
    rules.append(("beleidsoptie", "beleidsoptie", "conflicteert_met"))
    rules.append(("beleidsoptie", "beleidsoptie", "vervangt"))

    # politieke_input
    rules.append(("politieke_input", "doel", "draagt_bij_aan"))
    rules.append(("politieke_input", "doel", "vereist"))
    rules.append(("politieke_input", "instrument", "evalueert"))
    rules.append(("politieke_input", "instrument", "vereist"))
    rules.append(("politieke_input", "maatregel", "evalueert"))
    rules.append(("politieke_input", "maatregel", "vereist"))
    rules.append(("politieke_input", "probleem", "adresseert"))
    rules.append(("politieke_input", "beleidskader", "evalueert"))
    rules.append(("politieke_input", "politieke_input", "verwijst_naar"))
    rules.append(("politieke_input", "politieke_input", "vloeit_voort_uit"))

    # --- Universal patterns ---

    # Everything can be onderdeel_van a dossier
    for nt in ALL_NODE_TYPES:
        rules.append((nt, "dossier", "onderdeel_van"))

    # Everything can verwijst_naar a bron
    for nt in ALL_NODE_TYPES:
        if nt != "bron":
            rules.append((nt, "bron", "verwijst_naar"))

    # verwijst_naar: broad coverage (any -> any)
    for from_nt in ALL_NODE_TYPES:
        for to_nt in ALL_NODE_TYPES:
            rules.append((from_nt, to_nt, "verwijst_naar"))

    # Deduplicate
    return list(dict.fromkeys(rules))


def upgrade() -> None:
    rules = _build_rules()
    edge_schema_rule = sa.table(
        "edge_schema_rule",
        sa.column("from_node_type", sa.String),
        sa.column("to_node_type", sa.String),
        sa.column("edge_type_id", sa.String),
    )
    op.bulk_insert(
        edge_schema_rule,
        [
            {
                "from_node_type": from_nt,
                "to_node_type": to_nt,
                "edge_type_id": et_id,
            }
            for from_nt, to_nt, et_id in rules
        ],
    )


def downgrade() -> None:
    rules = _build_rules()
    conn = op.get_bind()
    edge_schema_rule = sa.table(
        "edge_schema_rule",
        sa.column("from_node_type", sa.String),
        sa.column("to_node_type", sa.String),
        sa.column("edge_type_id", sa.String),
    )
    # Bulk delete using OR conditions instead of one DELETE per rule.
    conditions = [
        sa.and_(
            edge_schema_rule.c.from_node_type == from_nt,
            edge_schema_rule.c.to_node_type == to_nt,
            edge_schema_rule.c.edge_type_id == et_id,
        )
        for from_nt, to_nt, et_id in rules
    ]
    if conditions:
        conn.execute(edge_schema_rule.delete().where(sa.or_(*conditions)))
