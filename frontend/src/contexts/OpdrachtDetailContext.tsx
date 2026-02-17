import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { nextModalSeq } from '@/utils/modalSeq';

interface OpdrachtDetailContextValue {
  openOpdrachtDetail: (id: string, parentLabel?: string) => void;
  opdrachtDetailId: string | null;
  opdrachtParentLabel: string | null;
  closeOpdrachtDetail: () => void;
  /** Monotonically increasing counter, bumped on every openOpdrachtDetail call. */
  opdrachtOpenSeq: number;
}

const OpdrachtDetailContext = createContext<OpdrachtDetailContextValue | null>(null);

export function useOpdrachtDetail() {
  const ctx = useContext(OpdrachtDetailContext);
  if (!ctx) throw new Error('useOpdrachtDetail must be used within OpdrachtDetailProvider');
  return ctx;
}

export function OpdrachtDetailProvider({ children }: { children: React.ReactNode }) {
  const [opdrachtId, setOpdrachtId] = useState<string | null>(null);
  const [parentLabel, setParentLabel] = useState<string | null>(null);
  const [openSeq, setOpenSeq] = useState(0);
  const location = useLocation();

  const openOpdrachtDetail = useCallback((id: string, label?: string) => {
    setOpdrachtId(id);
    setParentLabel(label ?? null);
    setOpenSeq(nextModalSeq());
  }, []);

  const closeOpdrachtDetail = useCallback(() => {
    setOpdrachtId(null);
    setParentLabel(null);
  }, []);

  // Close modal on route change
  useEffect(() => {
    setOpdrachtId(null);
    setParentLabel(null);
  }, [location.pathname]);

  return (
    <OpdrachtDetailContext.Provider value={{ openOpdrachtDetail, opdrachtDetailId: opdrachtId, opdrachtParentLabel: parentLabel, closeOpdrachtDetail, opdrachtOpenSeq: openSeq }}>
      {children}
    </OpdrachtDetailContext.Provider>
  );
}
