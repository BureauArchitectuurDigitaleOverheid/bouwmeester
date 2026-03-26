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

    // Visible IDs: own + managed (parent chain is computed server-side in the
    // backend OrgContext; here we provide a flat list for simple client-side checks).
    // TODO: The backend auth status endpoint should be extended with a full
    // visible_eenheid_ids list (section B7 of the plan) for complete parity
    // with the server-side OrgContext. For now, own + managed is sufficient.
    const visibleEenheidIds = [
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
