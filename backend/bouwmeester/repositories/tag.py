"""Repository for Tag CRUD and tree queries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.tag import NodeTag, Tag
from bouwmeester.schema.tag import TagCreate, TagUpdate


class TagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> list[Tag]:
        """Get all tags (flat list)."""
        stmt = select(Tag).order_by(Tag.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_tree(self) -> list[Tag]:
        """Get root tags with children eagerly loaded (recursive)."""
        stmt = (
            select(Tag)
            .where(Tag.parent_id.is_(None))
            .options(selectinload(Tag.children, recursion_depth=5))
            .order_by(Tag.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, tag_id: UUID) -> Tag | None:
        return await self.session.get(Tag, tag_id)

    async def get_by_name(self, name: str) -> Tag | None:
        stmt = select(Tag).where(Tag.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, query: str) -> list[Tag]:
        stmt = (
            select(Tag)
            .where(Tag.name.ilike(f"%{query}%"))
            .order_by(Tag.name)
            .limit(20)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: TagCreate) -> Tag:
        tag = Tag(**data.model_dump())
        self.session.add(tag)
        await self.session.flush()
        await self.session.refresh(tag)
        return tag

    async def update(self, tag_id: UUID, data: TagUpdate) -> Tag | None:
        tag = await self.session.get(Tag, tag_id)
        if tag is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(tag, key, value)
        await self.session.flush()
        await self.session.refresh(tag)
        return tag

    async def delete(self, tag_id: UUID) -> bool:
        tag = await self.session.get(Tag, tag_id)
        if tag is None:
            return False
        await self.session.delete(tag)
        await self.session.flush()
        return True

    async def get_by_node(self, node_id: UUID) -> list[NodeTag]:
        """Get all tags for a node, with tag relationship loaded."""
        stmt = (
            select(NodeTag)
            .where(NodeTag.node_id == node_id)
            .options(selectinload(NodeTag.tag))
            .order_by(NodeTag.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_tag_to_node(self, node_id: UUID, tag_id: UUID) -> NodeTag:
        node_tag = NodeTag(node_id=node_id, tag_id=tag_id)
        self.session.add(node_tag)
        await self.session.flush()
        await self.session.refresh(node_tag, ["tag"])
        return node_tag

    async def remove_tag_from_node(self, node_id: UUID, tag_id: UUID) -> bool:
        stmt = select(NodeTag).where(
            NodeTag.node_id == node_id, NodeTag.tag_id == tag_id
        )
        result = await self.session.execute(stmt)
        node_tag = result.scalar_one_or_none()
        if node_tag is None:
            return False
        await self.session.delete(node_tag)
        await self.session.flush()
        return True

    async def get_nodes_by_tag(self, tag_id: UUID) -> list[UUID]:
        """Get all node IDs that have a specific tag."""
        stmt = select(NodeTag.node_id).where(NodeTag.tag_id == tag_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
