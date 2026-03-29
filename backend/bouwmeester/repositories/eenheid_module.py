"""Repository for eenheid module toggles with hierarchy inheritance."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.eenheid_module import EenheidModule
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.schema.eenheid_module import VALID_MODULES


async def _walk_ancestors(
    db: AsyncSession, eenheid_ids: list[UUID]
) -> dict[UUID, list[UUID]]:
    """For each eenheid, return its ordered ancestor chain (parent, grandparent, ...).

    Uses batched queries — O(depth) queries regardless of eenheid count.
    """
    # First pass: batch-collect the full parent mapping for all reachable nodes
    parent_map: dict[UUID, UUID | None] = {}
    to_visit = set(eenheid_ids)

    while to_visit:
        # Only fetch nodes we haven't seen yet
        unknown = to_visit - parent_map.keys()
        if not unknown:
            break
        stmt = select(OrganisatieEenheid.id, OrganisatieEenheid.parent_id).where(
            OrganisatieEenheid.id.in_(unknown)
        )
        result = await db.execute(stmt)
        next_visit: set[UUID] = set()
        for eid, pid in result.all():
            parent_map[eid] = pid
            if pid is not None and pid not in parent_map:
                next_visit.add(pid)
        to_visit = next_visit

    # Second pass: walk the cached parent_map to build per-eenheid chains
    chains: dict[UUID, list[UUID]] = {}
    for eid in eenheid_ids:
        chain: list[UUID] = []
        current = eid
        visited: set[UUID] = set()
        while True:
            pid = parent_map.get(current)
            if pid is None or pid in visited:
                break
            chain.append(pid)
            visited.add(pid)
            current = pid
        chains[eid] = chain

    return chains


class EenheidModuleRepository:
    def __init__(self, db: AsyncSession):
        self.session = db

    async def get_all_disabled_modules_bulk(
        self, eenheid_ids: list[UUID]
    ) -> dict[UUID, set[str]]:
        """For multiple eenheden, return disabled module sets (with ancestors).

        Uses batched queries — O(depth) for the ancestor walk, then 1 query
        for all disabled modules.
        """
        if not eenheid_ids:
            return {}

        # Batch ancestor walk
        ancestor_map = await _walk_ancestors(self.session, eenheid_ids)

        # Collect all relevant IDs (self + ancestors) in one set
        all_ids: set[UUID] = set(eenheid_ids)
        for chain in ancestor_map.values():
            all_ids.update(chain)

        # Single query for all disabled modules
        stmt = select(EenheidModule.organisatie_eenheid_id, EenheidModule.module).where(
            EenheidModule.organisatie_eenheid_id.in_(all_ids),
            EenheidModule.enabled.is_(False),
        )
        result = await self.session.execute(stmt)
        disabled_by_eenheid: dict[UUID, set[str]] = {}
        for eid, mod in result.all():
            disabled_by_eenheid.setdefault(eid, set()).add(mod)

        # For each target, union disabled from self + ancestors
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
        if module not in VALID_MODULES:
            msg = f"Invalid module '{module}'"
            raise ValueError(msg)

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
        Uses batched queries via _walk_ancestors.
        """
        # Own toggles
        own_toggles: dict[str, bool] = {}
        for row in await self.list_for_eenheid(eenheid_id):
            own_toggles[row.module] = row.enabled

        # Ancestor chain with names (batched walk + single name query)
        ancestor_map = await _walk_ancestors(self.session, [eenheid_id])
        ancestor_ids = ancestor_map.get(eenheid_id, [])

        # Fetch ancestor names in one query
        ancestor_names: dict[UUID, str] = {}
        if ancestor_ids:
            name_stmt = select(OrganisatieEenheid.id, OrganisatieEenheid.naam).where(
                OrganisatieEenheid.id.in_(ancestor_ids)
            )
            for aid, naam in (await self.session.execute(name_stmt)).all():
                ancestor_names[aid] = naam

        # Fetch all ancestor disabled modules in one query
        ancestor_disables: dict[str, tuple[str, str]] = {}
        if ancestor_ids:
            anc_stmt = select(
                EenheidModule.organisatie_eenheid_id, EenheidModule.module
            ).where(
                EenheidModule.organisatie_eenheid_id.in_(ancestor_ids),
                EenheidModule.enabled.is_(False),
            )
            anc_rows = (await self.session.execute(anc_stmt)).all()

            # Walk ancestor_ids in order (closest first) so closest parent wins
            disabled_sources: dict[str, UUID] = {}
            for anc_eid, mod in anc_rows:
                if mod not in disabled_sources:
                    disabled_sources[mod] = anc_eid
            # But we want closest ancestor — rebuild using chain order
            disabled_sources_ordered: dict[str, UUID] = {}
            anc_disabled_set: dict[UUID, set[str]] = {}
            for aeid, mod in anc_rows:
                anc_disabled_set.setdefault(aeid, set()).add(mod)
            for anc_id in ancestor_ids:  # ordered closest-first
                for mod in anc_disabled_set.get(anc_id, set()):
                    if mod not in disabled_sources_ordered:
                        disabled_sources_ordered[mod] = anc_id

            for mod, anc_id in disabled_sources_ordered.items():
                ancestor_disables[mod] = (
                    str(anc_id),
                    ancestor_names.get(anc_id, ""),
                )

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
