import { useMemo } from 'react';
import type { AuthzResourceType } from '@/api/authz';
import { useCanEach } from '@/hooks/useCan';

interface EenheidGrant {
  eenheid_id: string;
  rol: string;
}

export interface EenheidGrantDecision {
  /** May the caller remove this eenheid's grant. */
  canRemove: boolean;
  /** Rols this grant may be set to, in `rolChoices` order; always includes the current one. */
  rols: string[];
}

/**
 * What the caller may do with the eenheden linked to a resource (grants to
 * everyone placed there), asked as the backend decides them: removing is
 * `resource_role:revoke` on the grant, changing the rol also needs
 * `resource_role:grant` of the new rol to that eenheid.
 */
export function useEenheidGrants(
  type: AuthzResourceType,
  id: string | null | undefined,
  eenheden: EenheidGrant[],
  rolChoices: string[],
): EenheidGrantDecision[] {
  const revokes = useMemo(
    () =>
      id
        ? eenheden.map((e) => ({ type, id, rol: e.rol, targetEenheidId: e.eenheid_id }))
        : [],
    [type, id, eenheden],
  );
  const grants = useMemo(
    () =>
      id
        ? eenheden.flatMap((e) =>
            rolChoices.map((rol) => ({ type, id, rol, targetEenheidId: e.eenheid_id })),
          )
        : [],
    [type, id, eenheden, rolChoices],
  );
  const { allowed: mayRevoke } = useCanEach('resource_role:revoke', revokes);
  const { allowed: mayGrant } = useCanEach('resource_role:grant', grants);

  return eenheden.map((e, i) => {
    const rols = rolChoices.filter(
      (rol, j) => rol === e.rol || (mayRevoke[i] && mayGrant[i * rolChoices.length + j]),
    );
    return {
      canRemove: mayRevoke[i] ?? false,
      rols: rols.includes(e.rol) ? rols : [e.rol, ...rols],
    };
  });
}
