"""Service for edge schema validation."""

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.repositories.edge_schema_rule import EdgeSchemaRuleRepository


class EdgeSchemaService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = EdgeSchemaRuleRepository(session)

    async def validate_edge(
        self,
        from_node_type: str,
        to_node_type: str,
        edge_type_id: str,
    ) -> str | None:
        """Validate an edge against the schema rules.

        Returns None if valid, or a Dutch error message if invalid.
        If no rules exist, all edges are allowed (backward compat).
        """
        if not await self.repo.has_any_rules():
            return None

        if await self.repo.is_valid_combination(
            from_node_type, to_node_type, edge_type_id
        ):
            return None

        return (
            f"Deze verbinding is niet toegestaan: "
            f"relatietype '{edge_type_id}' is niet geldig "
            f"tussen '{from_node_type}' en '{to_node_type}'."
        )
