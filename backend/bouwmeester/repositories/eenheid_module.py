"""Repository for eenheid module toggles with hierarchy inheritance."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.eenheid_module import EenheidModule
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.schema.eenheid_module import VALID_MODULES


class EenheidModuleRepository:
    def __init__(self, db: AsyncSession):
        self.session = db

    async def get_disabled_modules(
        self, eenheid_id: UUID, include_ancestors: bool = True
    ) -> dict[str, UUID | None]:
        """Return disabled modules for an eenheid, including inherited disables.

        Returns dict of {module_key: disabled_by_eenheid_id} where
        disabled_by_eenheid_id is the eenheid that set the disable
        (None should not occur, but kept for safety).
        """
        eenheid_ids = [eenheid_id]
        if include_ancestors:
            ancestors = await self._walk_parents([eenheid_id])
            eenheid_ids.extend(ancestors)

        stmt = select(EenheidModule).where(
            EenheidModule.organisatie_eenheid_id.in_(eenheid_ids),
            EenheidModule.enabled.is_(False),
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        disabled: dict[str, UUID] = {}
        for row in rows:
            if row.module not in disabled:
                disabled[row.module] = row.organisatie_eenheid_id
        return disabled

    async def get_all_disabled_modules_bulk(
        self, eenheid_ids: list[UUID]
    ) -> dict[UUID, set[str]]:
        """For multiple eenheden, return disabled module sets (with ancestors).

        Used by build_permission_context for batch processing.
        """
        if not eenheid_ids:
            return {}

        # Collect all ancestor IDs for all eenheden
        all_ids = set(eenheid_ids)
        ancestors = await self._walk_parents(list(all_ids))
        all_ids |= ancestors

        # Fetch all disabled modules for all relevant eenheden
        stmt = select(EenheidModule).where(
            EenheidModule.organisatie_eenheid_id.in_(all_ids),
            EenheidModule.enabled.is_(False),
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        # Build disabled set per source eenheid
        disabled_by_eenheid: dict[UUID, set[str]] = {eid: set() for eid in all_ids}
        for row in rows:
            disabled_by_eenheid.setdefault(row.organisatie_eenheid_id, set()).add(
                row.module
            )

        # Build ancestor chain for each target eenheid
        ancestor_map = await self._get_ancestor_chains(eenheid_ids)

        # For each target eenheid, union disabled from self + ancestors
        result_map: dict[UUID, set[str]] = {}
        for eid in eenheid_ids:
            disabled: set[str] = set()
            disabled |= disabled_by_eenheid.get(eid, set())
            for ancestor_id in ancestor_map.get(eid, []):
                disabled |= disabled_by_eenheid.get(ancestor_id, set())
            result_map[eid] = disabled

        return result_map

    async def list_for_eenheid(self, eenheid_id: UUID) -> list[EenheidModule]:
        """List own module toggles (not inherited) for an eenheid."""
        stmt = select(EenheidModule).where(
            EenheidModule.organisatie_eenheid_id == eenheid_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_module(
        self, eenheid_id: UUID, module: str, enabled: bool
    ) -> EenheidModule:
        """Set a module toggle for an eenheid (upsert)."""
        stmt = select(EenheidModule).where(
            EenheidModule.organisatie_eenheid_id == eenheid_id,
            EenheidModule.module == module,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.enabled = enabled
            await self.session.flush()
            return existing

        row = EenheidModule(
            organisatie_eenheid_id=eenheid_id,
            module=module,
            enabled=enabled,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete_module(self, eenheid_id: UUID, module: str) -> bool:
        """Delete a module override, reverting to default (enabled)."""
        stmt = select(EenheidModule).where(
            EenheidModule.organisatie_eenheid_id == eenheid_id,
            EenheidModule.module == module,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def get_full_config(self, eenheid_id: UUID) -> list[dict]:
        """Get full module config for an eenheid including inherited state.

        Returns a list of dicts with module, enabled, inherited_from,
        inherited_from_naam for all valid modules.
        """
        # Get own toggles
        own_toggles: dict[str, bool] = {}
        own_rows = await self.list_for_eenheid(eenheid_id)
        for row in own_rows:
            own_toggles[row.module] = row.enabled

        # Get ancestor disables with names
        ancestors = await self._get_ancestor_chain_with_names(eenheid_id)
        ancestor_disables: dict[str, tuple[str, str]] = {}
        for anc_id, anc_naam in ancestors:
            anc_stmt = select(EenheidModule).where(
                EenheidModule.organisatie_eenheid_id == anc_id,
                EenheidModule.enabled.is_(False),
            )
            anc_result = await self.session.execute(anc_stmt)
            for row in anc_result.scalars().all():
                if row.module not in ancestor_disables:
                    ancestor_disables[row.module] = (str(anc_id), anc_naam)

        configs = []
        for module in sorted(VALID_MODULES):
            inherited_from = None
            inherited_from_naam = None
            if module in ancestor_disables:
                inherited_from, inherited_from_naam = ancestor_disables[module]

            if module in own_toggles:
                enabled = own_toggles[module]
            elif inherited_from is not None:
                enabled = False
            else:
                enabled = True

            configs.append(
                {
                    "module": module,
                    "enabled": enabled,
                    "inherited_from": inherited_from,
                    "inherited_from_naam": inherited_from_naam,
                }
            )

        return configs

    async def _walk_parents(self, eenheid_ids: list[UUID]) -> set[UUID]:
        """Walk up parent chain, collecting all ancestor IDs."""
        collected: set[UUID] = set()
        to_visit = set(eenheid_ids)

        while to_visit:
            stmt = select(OrganisatieEenheid.id, OrganisatieEenheid.parent_id).where(
                OrganisatieEenheid.id.in_(to_visit)
            )
            result = await self.session.execute(stmt)
            rows = result.all()

            next_visit: set[UUID] = set()
            for row in rows:
                if row.parent_id is not None and row.parent_id not in collected:
                    collected.add(row.parent_id)
                    next_visit.add(row.parent_id)

            to_visit = next_visit

        return collected

    async def _get_ancestor_chains(
        self, eenheid_ids: list[UUID]
    ) -> dict[UUID, list[UUID]]:
        """For each eenheid, return ordered list of ancestor IDs."""
        result: dict[UUID, list[UUID]] = {eid: [] for eid in eenheid_ids}

        for eid in eenheid_ids:
            current = eid
            visited: set[UUID] = set()
            while True:
                stmt = select(OrganisatieEenheid.parent_id).where(
                    OrganisatieEenheid.id == current
                )
                res = await self.session.execute(stmt)
                parent_id = res.scalar_one_or_none()
                if parent_id is None or parent_id in visited:
                    break
                result[eid].append(parent_id)
                visited.add(parent_id)
                current = parent_id

        return result

    async def _get_ancestor_chain_with_names(
        self, eenheid_id: UUID
    ) -> list[tuple[UUID, str]]:
        """Walk up from eenheid, returning [(ancestor_id, naam), ...]."""
        chain: list[tuple[UUID, str]] = []
        current = eenheid_id
        visited: set[UUID] = set()

        while True:
            stmt = select(
                OrganisatieEenheid.parent_id,
            ).where(OrganisatieEenheid.id == current)
            result = await self.session.execute(stmt)
            parent_id = result.scalar_one_or_none()
            if parent_id is None or parent_id in visited:
                break

            name_stmt = select(OrganisatieEenheid.naam).where(
                OrganisatieEenheid.id == parent_id
            )
            name_result = await self.session.execute(name_stmt)
            naam = name_result.scalar_one_or_none() or ""

            chain.append((parent_id, naam))
            visited.add(parent_id)
            current = parent_id

        return chain
