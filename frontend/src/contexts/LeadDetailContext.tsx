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

  // A navigation closes the open lead, unless it came with one to open: an
  // old `/leads?lead=…` link redirects to the lead's initiatief and passes
  // the lead along in the navigation state. Opening it from the page itself
  // would lose the race, because this parent effect runs after the child's.
  const pendingLeadId = (location.state as { openLead?: string } | null)?.openLead ?? null;
  useEffect(() => {
    setLeadId(pendingLeadId);
    if (pendingLeadId) setOpenSeq(nextModalSeq());
    // Keyed on the path: the pending lead is read once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  return (
    <LeadDetailContext.Provider value={{ openLeadDetail, leadDetailId: leadId, closeLeadDetail, leadOpenSeq: openSeq }}>
      {children}
    </LeadDetailContext.Provider>
  );
}
