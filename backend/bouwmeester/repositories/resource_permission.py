"""Repository for unified resource permission operations."""

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select, union
from sqlalchemy.orm import selectinload

from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.base import BaseRepository


class ResourcePermissionRepository(BaseRepository[ResourcePermission]):
    model = ResourcePermission

    async def list_for_resource(
        self,
        resource_type: str,
        resource_id: UUID,
        include_eenheid: bool = False,
    ) -> list[ResourcePermission]:
        """List permissions for a resource.

        By default only loads the person relationship. Pass
        include_eenheid=True to also load the eenheid relationship
        (needed for initiatief detail views that show both).
        """
        stmt = (
            select(ResourcePermission)
            .where(
                ResourcePermission.resource_type == resource_type,
                ResourcePermission.resource_id == resource_id,
            )
            .options(selectinload(ResourcePermission.person))
            .order_by(ResourcePermission.rol, ResourcePermission.created_at)
        )
        if include_eenheid:
            stmt = stmt.options(selectinload(ResourcePermission.eenheid))
        else:
            # Only return person-scoped rows unless eenheid explicitly requested
            stmt = stmt.where(ResourcePermission.person_id.isnot(None))
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

    async def find_grants(
        self,
        resource_type: str,
        resource_id: UUID,
        *,
        person_id: UUID | None = None,
        eenheid_id: UUID | None = None,
    ) -> list[ResourcePermission]:
        """Grants on a resource for one person or one eenheid."""
        stmt = select(ResourcePermission).where(
            ResourcePermission.resource_type == resource_type,
            ResourcePermission.resource_id == resource_id,
        )
        if person_id is not None:
            stmt = stmt.where(ResourcePermission.person_id == person_id)
        if eenheid_id is not None:
            stmt = stmt.where(ResourcePermission.organisatie_eenheid_id == eenheid_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_roles_for_person_resource(
        self, person_id: UUID, resource_type: str, resource_id: UUID
    ) -> set[str]:
        """Return all roles a person has on a resource (direct + via eenheid)."""
        result = await self.session.execute(
            _person_roles_stmt(person_id, resource_type, resource_id)
        )
        return {rol for _rid, rol in result.all()}

    async def get_roles_for_person_by_resource(
        self, person_id: UUID, resource_type: str
    ) -> dict[UUID, set[str]]:
        """Every role a person has on resources of one type, in one query."""
        result = await self.session.execute(
            _person_roles_stmt(person_id, resource_type, None)
        )
        roles: dict[UUID, set[str]] = {}
        for rid, rol in result.all():
            roles.setdefault(rid, set()).add(rol)
        return roles

    async def list_for_person(self, person_id: UUID) -> list[ResourcePermission]:
        """Return all resource permissions for a person."""
        stmt = (
            select(ResourcePermission)
            .where(ResourcePermission.person_id == person_id)
            .options(selectinload(ResourcePermission.person))
            .order_by(ResourcePermission.resource_type, ResourcePermission.rol)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_eenheid(
        self, eenheid_id: UUID, resource_type: str | None = None
    ) -> list[ResourcePermission]:
        """Return all resource permissions for an eenheid."""
        stmt = select(ResourcePermission).where(
            ResourcePermission.organisatie_eenheid_id == eenheid_id,
        )
        if resource_type:
            stmt = stmt.where(ResourcePermission.resource_type == resource_type)
        stmt = stmt.order_by(ResourcePermission.resource_type, ResourcePermission.rol)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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


def _person_roles_stmt(person_id: UUID, resource_type: str, resource_id: UUID | None):
    """(resource_id, rol) a person holds, directly or through a placement."""
    today = date.today()
    on_resource = [ResourcePermission.resource_type == resource_type]
    if resource_id is not None:
        on_resource.append(ResourcePermission.resource_id == resource_id)

    direct_stmt = select(ResourcePermission.resource_id, ResourcePermission.rol).where(
        ResourcePermission.person_id == person_id, *on_resource
    )
    eenheid_stmt = (
        select(ResourcePermission.resource_id, ResourcePermission.rol)
        .join(
            PersonOrganisatieEenheid,
            PersonOrganisatieEenheid.organisatie_eenheid_id
            == ResourcePermission.organisatie_eenheid_id,
        )
        .where(
            *on_resource,
            ResourcePermission.organisatie_eenheid_id.isnot(None),
            PersonOrganisatieEenheid.person_id == person_id,
            PersonOrganisatieEenheid.start_datum <= today,
            or_(
                PersonOrganisatieEenheid.eind_datum.is_(None),
                PersonOrganisatieEenheid.eind_datum >= today,
            ),
        )
    )
    return union(direct_stmt, eenheid_stmt)
