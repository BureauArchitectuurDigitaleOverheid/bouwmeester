"""Shared SQL filter clauses for graph / corpus-node queries."""

from sqlalchemy import or_, select
from sqlalchemy.sql import ColumnElement

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge


def exclude_unconnected_pi() -> ColumnElement[bool]:
    """Return a WHERE clause that keeps all node types except orphan politieke_input.

    A politieke_input node is considered "orphan" when it has no edges at all
    (neither as source nor as target).
    """
    has_edge = CorpusNode.id.in_(
        select(Edge.from_node_id).union(select(Edge.to_node_id))
    )
    return or_(
        CorpusNode.node_type != "politieke_input",
        has_edge,
    )
