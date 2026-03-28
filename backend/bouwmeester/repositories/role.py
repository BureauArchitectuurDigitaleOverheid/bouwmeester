"""Repository for RBAC role and person-role operations."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.person import Person
from bouwmeester.models.role import Permission, PersonRole, Role, RolePermission


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_roles(self) -> list[Role]:
        stmt = select(Role).order_by(Role.rank.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_role(self, role_id: str) -> Role | None:
        return await self.session.get(Role, role_id)

    async def list_permissions(self) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.category, Permission.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_role_permission_ids(self, role_id: str) -> set[str]:
        """Return the set of permission IDs granted by a role."""
        stmt = select(RolePermission.permission_id).where(
            RolePermission.role_id == role_id
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_permissions_for_roles(self, role_ids: list[str]) -> set[str]:
        """Return the union of all permission IDs for the given roles."""
        if not role_ids:
            return set()
        stmt = select(RolePermission.permission_id).where(
            RolePermission.role_id.in_(role_ids)
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())


class PersonRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: UUID) -> PersonRole | None:
        stmt = (
            select(PersonRole)
            .where(PersonRole.id == id)
            .options(
                selectinload(PersonRole.person),
                selectinload(PersonRole.role),
                selectinload(PersonRole.organisatie_eenheid),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_person(self, person_id: UUID) -> list[PersonRole]:
        """Return all active role assignments for a person."""
        today = date.today()
        stmt = (
            select(PersonRole)
            .where(
                PersonRole.person_id == person_id,
                PersonRole.start_datum <= today,
                (PersonRole.eind_datum.is_(None)) | (PersonRole.eind_datum >= today),
            )
            .options(
                selectinload(PersonRole.person),
                selectinload(PersonRole.role),
                selectinload(PersonRole.organisatie_eenheid),
            )
            .order_by(PersonRole.role_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_eenheid(self, eenheid_id: UUID) -> list[PersonRole]:
        """Return all active role assignments for an eenheid."""
        today = date.today()
        stmt = (
            select(PersonRole)
            .where(
                PersonRole.organisatie_eenheid_id == eenheid_id,
                PersonRole.start_datum <= today,
                (PersonRole.eind_datum.is_(None)) | (PersonRole.eind_datum >= today),
            )
            .options(
                selectinload(PersonRole.person),
                selectinload(PersonRole.role),
            )
            .order_by(PersonRole.role_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def assign(
        self,
        person_id: UUID,
        role_id: str,
        organisatie_eenheid_id: UUID | None,
        granted_by_id: UUID | None,
        start_datum: date | None = None,
        eind_datum: date | None = None,
    ) -> PersonRole:
        pr = PersonRole(
            person_id=person_id,
            role_id=role_id,
            organisatie_eenheid_id=organisatie_eenheid_id,
            granted_by_id=granted_by_id,
            start_datum=start_datum or date.today(),
            eind_datum=eind_datum,
        )
        self.session.add(pr)
        await self.session.flush()
        # Reload with relationships
        return await self.get_by_id(pr.id)  # type: ignore[return-value]

    async def revoke(self, id: UUID) -> bool:
        pr = await self.session.get(PersonRole, id)
        if pr is None:
            return False
        await self.session.delete(pr)
        await self.session.flush()
        return True

    async def get_super_admins(self) -> list[Person]:
        """Return all persons with an active super_admin role."""
        stmt = (
            select(Person)
            .join(PersonRole, PersonRole.person_id == Person.id)
            .where(
                PersonRole.role_id == "super_admin",
                PersonRole.eind_datum.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_super_admin_ids(self) -> set[UUID]:
        """Return person IDs of all active super_admins."""
        stmt = select(PersonRole.person_id).where(
            PersonRole.role_id == "super_admin",
            PersonRole.eind_datum.is_(None),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_active_role_ids_for_person(
        self, person_id: UUID
    ) -> tuple[list[str], dict[UUID, list[str]]]:
        """Return (system_roles, {eenheid_id: [role_ids]}) for active assignments."""
        today = date.today()
        stmt = select(PersonRole.role_id, PersonRole.organisatie_eenheid_id).where(
            PersonRole.person_id == person_id,
            PersonRole.start_datum <= today,
            (PersonRole.eind_datum.is_(None)) | (PersonRole.eind_datum >= today),
        )
        result = await self.session.execute(stmt)

        system_roles: list[str] = []
        scoped_roles: dict[UUID, list[str]] = {}
        for role_id, eenheid_id in result.all():
            if eenheid_id is None:
                system_roles.append(role_id)
            else:
                scoped_roles.setdefault(eenheid_id, []).append(role_id)

        return system_roles, scoped_roles
