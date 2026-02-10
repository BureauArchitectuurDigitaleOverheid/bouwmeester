"""Service layer for CorpusNode operations."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.beleidskader import Beleidskader
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.doel import Doel
from bouwmeester.models.dossier import Dossier
from bouwmeester.models.instrument import Instrument
from bouwmeester.models.maatregel import Maatregel
from bouwmeester.models.node_status import CorpusNodeStatus
from bouwmeester.models.node_title import CorpusNodeTitle
from bouwmeester.models.politieke_input import PolitiekeInput
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
        type_factories = {
            "dossier": lambda nid: Dossier(id=nid, fase="verkenning"),
            "doel": lambda nid: Doel(id=nid, type="operationeel"),
            "instrument": lambda nid: Instrument(id=nid, type="overig"),
            "beleidskader": lambda nid: Beleidskader(id=nid, scope="nationaal"),
            "maatregel": lambda nid: Maatregel(id=nid),
            "politieke_input": lambda nid: PolitiekeInput(id=nid, type="toezegging"),
        }
        factory = type_factories.get(data.node_type.value)
        if factory:
            self.session.add(factory(node.id))

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
