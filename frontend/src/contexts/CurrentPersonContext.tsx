import { createContext, useContext, useState, useMemo, useCallback } from 'react';
import type { ReactNode } from 'react';
import { usePeople } from '@/hooks/usePeople';
import { useAuth } from '@/contexts/AuthContext';
import type { Person } from '@/types';

const STORAGE_KEY = 'current-person-id';

interface CurrentPersonContextValue {
  /** The active person (the SSO-linked user, or the dev-mode selection). */
  currentPerson: Person | null;
  /** Dev mode only: select a person by ID (persisted to localStorage). */
  setDevPersonId: (id: string | null) => void;
  /** All people (for the dev-mode picker). */
  people: Person[];
}

const CurrentPersonContext = createContext<CurrentPersonContextValue>({
  currentPerson: null,
  setDevPersonId: () => {},
  people: [],
});

export function CurrentPersonProvider({ children }: { children: ReactNode }) {
  const { oidcConfigured, person: authPerson, viewAsNonAdmin } = useAuth();
  const { data: people } = usePeople();

  // The SSO-linked person ID (from auth context)
  const authPersonId = oidcConfigured ? (authPerson?.id ?? null) : null;

  // Dev mode only: localStorage-backed person selection.
  const [devPersonId, setDevPersonIdState] = useState<string | null>(() => {
    if (!oidcConfigured) {
      return localStorage.getItem(STORAGE_KEY);
    }
    return null;
  });

  const setDevPersonId = useCallback(
    (id: string | null) => {
      // Only effective in dev mode (no OIDC)
      if (oidcConfigured) return;
      setDevPersonIdState(id);
      if (id) {
        localStorage.setItem(STORAGE_KEY, id);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    },
    [oidcConfigured],
  );

  // In SSO mode, use the authenticated person; in dev mode, use localStorage selection.
  const effectiveId = oidcConfigured ? authPersonId : devPersonId;

  const currentPerson = useMemo(() => {
    const found = (people ?? []).find((p) => p.id === effectiveId) ?? null;
    if (found && viewAsNonAdmin) {
      return { ...found, is_admin: false };
    }
    return found;
  }, [people, effectiveId, viewAsNonAdmin]);

  const value = useMemo(
    () => ({
      currentPerson,
      setDevPersonId,
      people: people ?? [],
    }),
    [currentPerson, setDevPersonId, people],
  );

  return (
    <CurrentPersonContext.Provider value={value}>
      {children}
    </CurrentPersonContext.Provider>
  );
}

export function useCurrentPerson() {
  return useContext(CurrentPersonContext);
}
