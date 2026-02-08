"""add indexes on FK columns and unique constraints

Revision ID: c43f045e002f
Revises: 03bc23d0b7e2
Create Date: 2026-02-08 20:42:18.469028

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c43f045e002f"
down_revision: str | None = "03bc23d0b7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_corpus_node_node_type"),
        "corpus_node",
        ["node_type"],
    )
    op.create_index(
        op.f("ix_edge_edge_type_id"),
        "edge",
        ["edge_type_id"],
    )
    op.create_index(
        op.f("ix_edge_from_node_id"),
        "edge",
        ["from_node_id"],
    )
    op.create_index(
        op.f("ix_edge_to_node_id"),
        "edge",
        ["to_node_id"],
    )
    op.create_unique_constraint(
        "uq_edge_from_to_type",
        "edge",
        ["from_node_id", "to_node_id", "edge_type_id"],
    )
    op.create_index(
        op.f("ix_node_stakeholder_node_id"),
        "node_stakeholder",
        ["node_id"],
    )
    op.create_index(
        op.f("ix_node_stakeholder_person_id"),
        "node_stakeholder",
        ["person_id"],
    )
    op.create_unique_constraint(
        "uq_node_stakeholder_node_person_rol",
        "node_stakeholder",
        ["node_id", "person_id", "rol"],
    )
    op.create_index(
        op.f("ix_task_assignee_id"),
        "task",
        ["assignee_id"],
    )
    op.create_index(
        op.f("ix_task_node_id"),
        "task",
        ["node_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_node_id"), table_name="task")
    op.drop_index(op.f("ix_task_assignee_id"), table_name="task")
    op.drop_constraint(
        "uq_node_stakeholder_node_person_rol",
        "node_stakeholder",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_node_stakeholder_person_id"),
        table_name="node_stakeholder",
    )
    op.drop_index(
        op.f("ix_node_stakeholder_node_id"),
        table_name="node_stakeholder",
    )
    op.drop_constraint(
        "uq_edge_from_to_type",
        "edge",
        type_="unique",
    )
    op.drop_index(op.f("ix_edge_to_node_id"), table_name="edge")
    op.drop_index(op.f("ix_edge_from_node_id"), table_name="edge")
    op.drop_index(op.f("ix_edge_edge_type_id"), table_name="edge")
    op.drop_index(
        op.f("ix_corpus_node_node_type"),
        table_name="corpus_node",
    )
