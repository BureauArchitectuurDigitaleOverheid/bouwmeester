import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

interface OpdrachtCreateDefaults {
  instrument_id?: string;
}

interface OpdrachtCreateContextValue {
  openOpdrachtCreate: (defaults?: OpdrachtCreateDefaults) => void;
  closeOpdrachtCreate: () => void;
  isOpen: boolean;
  defaults: OpdrachtCreateDefaults | null;
}

const OpdrachtCreateContext = createContext<OpdrachtCreateContextValue | null>(null);

export function useOpdrachtCreate() {
  const ctx = useContext(OpdrachtCreateContext);
  if (!ctx) throw new Error('useOpdrachtCreate must be used within OpdrachtCreateProvider');
  return ctx;
}

export function OpdrachtCreateProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [defaults, setDefaults] = useState<OpdrachtCreateDefaults | null>(null);
  const location = useLocation();

  const openOpdrachtCreate = useCallback((d?: OpdrachtCreateDefaults) => {
    setDefaults(d ?? null);
    setIsOpen(true);
  }, []);

  const closeOpdrachtCreate = useCallback(() => {
    setIsOpen(false);
    setDefaults(null);
  }, []);

  // Close on route change
  useEffect(() => {
    setIsOpen(false);
    setDefaults(null);
  }, [location.pathname]);

  return (
    <OpdrachtCreateContext.Provider value={{ openOpdrachtCreate, closeOpdrachtCreate, isOpen, defaults }}>
      {children}
    </OpdrachtCreateContext.Provider>
  );
}
