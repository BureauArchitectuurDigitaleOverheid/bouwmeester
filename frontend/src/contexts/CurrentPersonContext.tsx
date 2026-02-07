import { createContext, useContext, useState, useMemo, useCallback } from 'react';
import type { ReactNode } from 'react';
import { usePeople } from '@/hooks/usePeople';
import type { Person } from '@/types';

const STORAGE_KEY = 'current-person-id';

interface CurrentPersonContextValue {
  currentPerson: Person | null;
  setCurrentPersonId: (id: string | null) => void;
  people: Person[];
}

const CurrentPersonContext = createContext<CurrentPersonContextValue>({
  currentPerson: null,
  setCurrentPersonId: () => {},
  people: [],
});

export function CurrentPersonProvider({ children }: { children: ReactNode }) {
  const [personId, setPersonId] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY),
  );
  const { data: people } = usePeople();

  const setCurrentPersonId = useCallback((id: string | null) => {
    setPersonId(id);
    if (id) {
      localStorage.setItem(STORAGE_KEY, id);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  const currentPerson = useMemo(
    () => (people ?? []).find((p) => p.id === personId) ?? null,
    [people, personId],
  );

  const value = useMemo(
    () => ({ currentPerson, setCurrentPersonId, people: people ?? [] }),
    [currentPerson, setCurrentPersonId, people],
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
