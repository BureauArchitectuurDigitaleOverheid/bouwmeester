import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

interface OpdrachtDetailContextValue {
  openOpdrachtDetail: (id: string) => void;
  opdrachtDetailId: string | null;
  closeOpdrachtDetail: () => void;
}

const OpdrachtDetailContext = createContext<OpdrachtDetailContextValue | null>(null);

export function useOpdrachtDetail() {
  const ctx = useContext(OpdrachtDetailContext);
  if (!ctx) throw new Error('useOpdrachtDetail must be used within OpdrachtDetailProvider');
  return ctx;
}

export function OpdrachtDetailProvider({ children }: { children: React.ReactNode }) {
  const [opdrachtId, setOpdrachtId] = useState<string | null>(null);
  const location = useLocation();

  const openOpdrachtDetail = useCallback((id: string) => {
    setOpdrachtId(id);
  }, []);

  const closeOpdrachtDetail = useCallback(() => {
    setOpdrachtId(null);
  }, []);

  // Close modal on route change
  useEffect(() => {
    setOpdrachtId(null);
  }, [location.pathname]);

  return (
    <OpdrachtDetailContext.Provider value={{ openOpdrachtDetail, opdrachtDetailId: opdrachtId, closeOpdrachtDetail }}>
      {children}
    </OpdrachtDetailContext.Provider>
  );
}
