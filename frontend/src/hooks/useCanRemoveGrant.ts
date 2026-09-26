import type { AuthzResourceType } from '@/api/authz';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useCan } from '@/hooks/useCan';

export interface GrantRef {
  resourceType: AuthzResourceType;
  resourceId: string;
  rol: string;
  /** The person holding the grant; null for a grant to an eenheid. */
  personId: string | null;
}

/**
 * May the caller remove this grant (a member, contact or betrokkene)?
 *
 * Stopgap until the evaluation endpoint answers a revoke question itself: it
 * follows backend `require_can_change_resource_role`. The last eigenaar
 * never goes (the backend answers 409), leaving yourself is always allowed,
 * anything else needs the authority to hand out that rol to that person.
 * Pass `lastEigenaar` where the caller can see the other grants.
 */
export function useCanRemoveGrant(grant: GrantRef, { lastEigenaar = false } = {}): boolean {
  const { currentPerson } = useCurrentPerson();
  const own = grant.personId !== null && grant.personId === currentPerson?.id;
  const { allowed } = useCan(
    'resource_role:grant',
    own || lastEigenaar
      ? null
      : {
          type: grant.resourceType,
          id: grant.resourceId,
          rol: grant.rol,
          targetPersonId: grant.personId ?? undefined,
        },
  );
  if (lastEigenaar) return false;
  return own || allowed;
}
