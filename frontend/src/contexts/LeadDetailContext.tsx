import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { nextModalSeq } from '@/utils/modalSeq';

interface LeadDetailContextValue {
  openLeadDetail: (leadId: string) => void;
  leadDetailId: string | null;
  closeLeadDetail: () => void;
  leadOpenSeq: number;
}

const LeadDetailContext = createContext<LeadDetailContextValue | null>(null);

export function useLeadDetail() {
  const ctx = useContext(LeadDetailContext);
  if (!ctx) throw new Error('useLeadDetail must be used within LeadDetailProvider');
  return ctx;
}

export function LeadDetailProvider({ children }: { children: React.ReactNode }) {
  const [leadId, setLeadId] = useState<string | null>(null);
  const [openSeq, setOpenSeq] = useState(0);
  const location = useLocation();

  const openLeadDetail = useCallback((id: string) => {
    setLeadId(id);
    setOpenSeq(nextModalSeq());
  }, []);

  const closeLeadDetail = useCallback(() => {
    setLeadId(null);
  }, []);

  useEffect(() => {
    setLeadId(null);
  }, [location.pathname]);

  return (
    <LeadDetailContext.Provider value={{ openLeadDetail, leadDetailId: leadId, closeLeadDetail, leadOpenSeq: openSeq }}>
      {children}
    </LeadDetailContext.Provider>
  );
}
