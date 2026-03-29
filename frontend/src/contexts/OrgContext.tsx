import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useAuth } from '@/contexts/AuthContext';

interface OrgEenheid {
  id: string;
  naam: string;
  type: string | null;
}

interface OrgContextValue {
  /** The user's own org eenheden (from auth status). */
  ownEenheden: OrgEenheid[];
  /** All visible eenheid IDs (own + parents + managed sub-eenheden). */
  visibleEenheidIds: string[];
  /** Eenheden where the user is manager. */
  managedEenheden: OrgEenheid[];
  /** Whether the user is a manager of any eenheid. */
  isManager: boolean;
  /** Whether user needs to request org placement (no eenheden yet). */
  needsPlacement: boolean;
}

const OrgContext = createContext<OrgContextValue>({
  ownEenheden: [],
  visibleEenheidIds: [],
  managedEenheden: [],
  isManager: false,
  needsPlacement: false,
});

export function OrgContextProvider({ children }: { children: ReactNode }) {
  const { person } = useAuth();

  const value = useMemo<OrgContextValue>(() => {
    const ownEenheden = person?.organisatie_eenheden ?? [];
    const managedEenheden = person?.managed_eenheden ?? [];
    const backendVisibleIds = person?.visible_eenheid_ids;

    // Use backend-provided visible_eenheid_ids which include the full
    // parent chain, managed sub-trees, and shared access grants.
    // "*" means admin with full visibility.
    // Only fall back to own+managed when the field is absent (undefined),
    // not when the backend explicitly returns an empty list.
    const visibleEenheidIds =
      backendVisibleIds !== undefined
        ? backendVisibleIds
        : [
            ...new Set([
              ...ownEenheden.map((e) => e.id),
              ...managedEenheden.map((e) => e.id),
            ]),
          ];

    return {
      ownEenheden,
      visibleEenheidIds,
      managedEenheden,
      isManager: managedEenheden.length > 0,
      needsPlacement: person?.needs_placement ?? false,
    };
  }, [person]);

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrgContext(): OrgContextValue {
  return useContext(OrgContext);
}
