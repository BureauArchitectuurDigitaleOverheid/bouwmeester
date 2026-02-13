"""seed reference data edge types and tags

Revision ID: e1bfb6704ba8
Revises: 97ccf3b922b4
Create Date: 2026-02-13 07:24:03.800806

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1bfb6704ba8"
down_revision: str | None = "97ccf3b922b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# -- Reference data ----------------------------------------------------------

EDGE_TYPES = [
    (
        "implementeert",
        "Implementeert",
        "Implements",
        "Het ene item implementeert of voert het andere uit.",
    ),
    (
        "draagt_bij_aan",
        "Draagt bij aan",
        "Contributes to",
        "Het ene item draagt bij aan de realisatie van het andere.",
    ),
    (
        "vloeit_voort_uit",
        "Vloeit voort uit",
        "Derives from",
        "Het ene item vloeit voort uit of is afgeleid van het andere.",
    ),
    (
        "conflicteert_met",
        "Conflicteert met",
        "Conflicts with",
        "Spanningen of tegenstrijdigheden tussen twee items.",
    ),
    (
        "verwijst_naar",
        "Verwijst naar",
        "References",
        "Het ene item verwijst expliciet naar het andere.",
    ),
    (
        "vereist",
        "Vereist",
        "Requires",
        "Het ene item is een voorwaarde voor het andere.",
    ),
    (
        "evalueert",
        "Evalueert",
        "Evaluates",
        "Het ene item beoordeelt of evalueert het andere.",
    ),
    (
        "vervangt",
        "Vervangt",
        "Replaces",
        "Het ene item vervangt het andere.",
    ),
    (
        "onderdeel_van",
        "Onderdeel van",
        "Part of",
        "Het ene item is een onderdeel of deelstrategie van het andere.",
    ),
    (
        "leidt_tot",
        "Leidt tot",
        "Leads to",
        "Causale relatie: het ene item leidt tot het andere "
        "(probleem\u2192doel, maatregel\u2192effect).",
    ),
    (
        "adresseert",
        "Adresseert",
        "Addresses",
        "Het ene item adresseert of pakt het andere aan "
        "(maatregel/instrument\u2192probleem).",
    ),
    (
        "meet",
        "Meet",
        "Measures",
        "Het ene item meet of monitort het andere (effect\u2192indicator/doel).",
    ),
]

# Tags: (name, parent_name_or_None)
ROOT_TAGS = [
    "digitalisering",
    "overheid",
    "veiligheid",
    "wetgeving",
    "europees",
    "data",
    "inclusie",
    "duurzaamheid",
]

CHILD_TAGS = [
    # digitalisering children
    ("digitalisering/AI", "digitalisering"),
    ("digitalisering/algoritmen", "digitalisering"),
    ("digitalisering/cloud", "digitalisering"),
    ("digitalisering/identiteit", "digitalisering"),
    ("digitalisering/infrastructuur", "digitalisering"),
    ("digitalisering/open-source", "digitalisering"),
    # overheid children
    ("overheid/digitale-dienstverlening", "overheid"),
    ("overheid/fysieke-dienstverlening", "overheid"),
    ("overheid/CIO-stelsel", "overheid"),
    ("overheid/architectuur", "overheid"),
    ("overheid/IT-personeel", "overheid"),
    ("overheid/rijksbrede-ICT", "overheid"),
    # veiligheid children
    ("veiligheid/cybersecurity", "veiligheid"),
    ("veiligheid/privacy", "veiligheid"),
    ("veiligheid/BIO", "veiligheid"),
    # wetgeving children
    ("wetgeving/WDO", "wetgeving"),
    ("wetgeving/AI-Act", "wetgeving"),
    ("wetgeving/Woo", "wetgeving"),
    # europees children
    ("europees/eIDAS", "europees"),
    ("europees/EUDIW", "europees"),
    ("europees/Data-Governance-Act", "europees"),
    # data children
    ("data/federatief-datastelsel", "data"),
    ("data/data-spaces", "data"),
    ("data/open-data", "data"),
    ("data/datakwaliteit", "data"),
    # inclusie children
    ("inclusie/digitale-kloof", "inclusie"),
    ("inclusie/toegankelijkheid", "inclusie"),
]

GRANDCHILD_TAGS = [
    ("digitalisering/AI/generatieve-AI", "digitalisering/AI"),
]


def upgrade() -> None:
    # -- Edge types (idempotent) ----------------------------------------------
    for id_, label_nl, label_en, description in EDGE_TYPES:
        vals = f"{_q(id_)}, {_q(label_nl)}, {_q(label_en)}, {_q(description)}, false"
        op.execute(
            f"INSERT INTO edge_type "
            f"(id, label_nl, label_en, description, is_custom) "
            f"VALUES ({vals}) "
            f"ON CONFLICT (id) DO NOTHING"
        )

    # -- Tags (idempotent, 3 passes for hierarchy) ---------------------------

    # Pass 1: root tags
    for name in ROOT_TAGS:
        op.execute(
            f"INSERT INTO tag (id, name) "
            f"VALUES (gen_random_uuid(), {_q(name)}) "
            f"ON CONFLICT (name) DO NOTHING"
        )

    # Pass 2: level-1 children
    for name, parent_name in CHILD_TAGS:
        op.execute(
            f"INSERT INTO tag (id, name, parent_id) "
            f"VALUES (gen_random_uuid(), {_q(name)}, "
            f"(SELECT id FROM tag WHERE name = {_q(parent_name)})) "
            f"ON CONFLICT (name) DO NOTHING"
        )

    # Pass 3: level-2 grandchildren
    for name, parent_name in GRANDCHILD_TAGS:
        op.execute(
            f"INSERT INTO tag (id, name, parent_id) "
            f"VALUES (gen_random_uuid(), {_q(name)}, "
            f"(SELECT id FROM tag WHERE name = {_q(parent_name)})) "
            f"ON CONFLICT (name) DO NOTHING"
        )


def downgrade() -> None:
    # Remove edge types that are not referenced by any edge
    ids = ", ".join(_q(et[0]) for et in EDGE_TYPES)
    op.execute(
        f"DELETE FROM edge_type WHERE id IN ({ids}) "
        f"AND id NOT IN (SELECT DISTINCT edge_type_id FROM edge)"
    )

    # Remove tags that are not referenced by any node_tag
    # (grandchildren first, then children, then roots to respect parent FK)
    for name, _ in GRANDCHILD_TAGS:
        op.execute(
            f"DELETE FROM tag WHERE name = {_q(name)} "
            f"AND id NOT IN (SELECT tag_id FROM node_tag)"
        )
    for name, _ in CHILD_TAGS:
        op.execute(
            f"DELETE FROM tag WHERE name = {_q(name)} "
            f"AND id NOT IN (SELECT tag_id FROM node_tag) "
            f"AND id NOT IN (SELECT parent_id FROM tag WHERE parent_id IS NOT NULL)"
        )
    for name in ROOT_TAGS:
        op.execute(
            f"DELETE FROM tag WHERE name = {_q(name)} "
            f"AND id NOT IN (SELECT tag_id FROM node_tag) "
            f"AND id NOT IN (SELECT parent_id FROM tag WHERE parent_id IS NOT NULL)"
        )


def _q(s: str) -> str:
    """Quote a string literal for SQL, escaping single quotes."""
    return "'" + s.replace("'", "''") + "'"
