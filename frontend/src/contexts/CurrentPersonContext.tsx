import { createContext, useContext, useState, useMemo, useCallback } from 'react';
import type { ReactNode } from 'react';
import { usePeople } from '@/hooks/usePeople';
import { useAuth } from '@/contexts/AuthContext';
import type { Person } from '@/types';

const STORAGE_KEY = 'current-person-id';

interface CurrentPersonContextValue {
  /** The active person (either the SSO-linked user or the "view as" override). */
  currentPerson: Person | null;
  /** Switch to viewing as a different person (or null to reset). */
  setCurrentPersonId: (id: string | null) => void;
  /** All people (for the picker dropdown). */
  people: Person[];
  /** True when viewing as someone other than the authenticated user. */
  isViewingAsOther: boolean;
  /** Reset to the authenticated user's own Person. */
  resetToSelf: () => void;
}

const CurrentPersonContext = createContext<CurrentPersonContextValue>({
  currentPerson: null,
  setCurrentPersonId: () => {},
  people: [],
  isViewingAsOther: false,
  resetToSelf: () => {},
});

export function CurrentPersonProvider({ children }: { children: ReactNode }) {
  const { oidcConfigured, person: authPerson } = useAuth();
  const { data: people } = usePeople();

  // The SSO-linked person ID (from auth context)
  const authPersonId = oidcConfigured ? (authPerson?.id ?? null) : null;

  // Override person ID — "view as" in SSO mode, or the localStorage picker in dev mode.
  const [overrideId, setOverrideId] = useState<string | null>(() => {
    if (!oidcConfigured) {
      return localStorage.getItem(STORAGE_KEY);
    }
    return null;
  });

  const setCurrentPersonId = useCallback(
    (id: string | null) => {
      if (oidcConfigured) {
        // In SSO mode: setting to null or to your own ID resets to self
        setOverrideId(id === authPersonId ? null : id);
      } else {
        // Dev mode: persist in localStorage
        setOverrideId(id);
        if (id) {
          localStorage.setItem(STORAGE_KEY, id);
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    },
    [oidcConfigured, authPersonId],
  );

  const resetToSelf = useCallback(() => {
    setOverrideId(null);
  }, []);

  // The effective person ID: override takes priority, then auth person, then dev localStorage
  const effectiveId = overrideId ?? authPersonId;

  const currentPerson = useMemo(
    () => (people ?? []).find((p) => p.id === effectiveId) ?? null,
    [people, effectiveId],
  );

  const isViewingAsOther = oidcConfigured && !!overrideId && overrideId !== authPersonId;

  const value = useMemo(
    () => ({
      currentPerson,
      setCurrentPersonId,
      people: people ?? [],
      isViewingAsOther,
      resetToSelf,
    }),
    [currentPerson, setCurrentPersonId, people, isViewingAsOther, resetToSelf],
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
