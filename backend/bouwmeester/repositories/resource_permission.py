"""Repository for unified resource permission operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.base import BaseRepository


class ResourcePermissionRepository(BaseRepository[ResourcePermission]):
    model = ResourcePermission

    async def list_for_resource(
        self, resource_type: str, resource_id: UUID
    ) -> list[ResourcePermission]:
        stmt = (
            select(ResourcePermission)
            .where(
                ResourcePermission.resource_type == resource_type,
                ResourcePermission.resource_id == resource_id,
            )
            .options(selectinload(ResourcePermission.person))
            .order_by(ResourcePermission.rol, ResourcePermission.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_person(self, rp_id: UUID) -> ResourcePermission | None:
        stmt = (
            select(ResourcePermission)
            .where(ResourcePermission.id == rp_id)
            .options(selectinload(ResourcePermission.person))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_permission(
        self,
        person_id: UUID,
        resource_type: str,
        resource_id: UUID,
        rol: str,
    ) -> ResourcePermission:
        rp = ResourcePermission(
            person_id=person_id,
            resource_type=resource_type,
            resource_id=resource_id,
            rol=rol,
        )
        self.session.add(rp)
        await self.session.flush()
        return await self.get_with_person(rp.id)  # type: ignore[return-value]

    async def get_roles_for_person_resource(
        self, person_id: UUID, resource_type: str, resource_id: UUID
    ) -> set[str]:
        """Return all roles a person has on a specific resource."""
        stmt = select(ResourcePermission.rol).where(
            ResourcePermission.person_id == person_id,
            ResourcePermission.resource_type == resource_type,
            ResourcePermission.resource_id == resource_id,
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_resource_ids_for_person(
        self, person_id: UUID, resource_type: str
    ) -> dict[UUID, set[str]]:
        """Return {resource_id: {roles}} for a person's resources."""
        stmt = select(ResourcePermission.resource_id, ResourcePermission.rol).where(
            ResourcePermission.person_id == person_id,
            ResourcePermission.resource_type == resource_type,
        )
        result = await self.session.execute(stmt)
        mapping: dict[UUID, set[str]] = {}
        for resource_id, rol in result.all():
            mapping.setdefault(resource_id, set()).add(rol)
        return mapping
