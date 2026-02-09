"""Service layer for CorpusNode operations."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.node_status import CorpusNodeStatus
from bouwmeester.models.node_title import CorpusNodeTitle
from bouwmeester.repositories.corpus_node import CorpusNodeRepository
from bouwmeester.schema.corpus_node import CorpusNodeCreate, CorpusNodeUpdate


class NodeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CorpusNodeRepository(session)

    async def get(self, id: UUID) -> CorpusNode | None:
        return await self.repo.get(id)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        node_type: str | None = None,
    ) -> list[CorpusNode]:
        return await self.repo.get_all(skip=skip, limit=limit, node_type=node_type)

    async def create(self, data: CorpusNodeCreate) -> CorpusNode:
        node = await self.repo.create(data)

        # Create the type-specific sub-record with defaults.
        # These tables extend corpus_node with extra columns specific
        # to each node type, using the same id as foreign key.
        type_table_map = {
            "dossier": "dossier",
            "doel": "doel",
            "instrument": "instrument",
            "beleidskader": "beleidskader",
            "maatregel": "maatregel",
            "politieke_input": "politieke_input",
        }
        table_name = type_table_map.get(data.node_type.value)
        if table_name:
            from sqlalchemy import text

            # Insert a row into the type-specific table with the same id.
            # Each type table has required columns with defaults or NULLable fields.
            defaults = {
                "dossier": "fase = 'verkenning'",
                "doel": "type = 'operationeel'",
                "instrument": "type = 'overig'",
                "beleidskader": "scope = 'nationaal'",
                "maatregel": "",
                "politieke_input": "type = 'toezegging'",
            }
            cols = defaults.get(table_name, "")
            if cols:
                stmt = text(
                    f"INSERT INTO {table_name} (id, {cols.split(' = ')[0]}) "
                    f"VALUES (:id, :val)"
                )
                await self.session.execute(
                    stmt,
                    {"id": str(node.id), "val": cols.split(" = ")[1].strip("'")},
                )
            else:
                stmt = text(f"INSERT INTO {table_name} (id) VALUES (:id)")
                await self.session.execute(stmt, {"id": str(node.id)})

        return node

    async def update(self, id: UUID, data: CorpusNodeUpdate) -> CorpusNode | None:
        return await self.repo.update(id, data)

    async def delete(self, id: UUID) -> bool:
        return await self.repo.delete(id)

    async def get_neighbors(self, id: UUID) -> dict:
        return await self.repo.get_neighbors(id)

    async def get_graph(self, node_id: UUID, depth: int = 2) -> dict:
        return await self.repo.get_graph(node_id, depth)

    async def count(self, node_type: str | None = None) -> int:
        return await self.repo.count(node_type)

    async def get_title_history(self, node_id: UUID) -> list[CorpusNodeTitle]:
        return await self.repo.get_title_history(node_id)

    async def get_status_history(self, node_id: UUID) -> list[CorpusNodeStatus]:
        return await self.repo.get_status_history(node_id)
