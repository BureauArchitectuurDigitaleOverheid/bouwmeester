import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { nextModalSeq } from '@/utils/modalSeq';

interface NodeDetailContextValue {
  openNodeDetail: (nodeId: string, parentLabel?: string) => void;
  nodeDetailId: string | null;
  nodeParentLabel: string | null;
  closeNodeDetail: () => void;
  /** Monotonically increasing counter, bumped on every openNodeDetail call. */
  nodeOpenSeq: number;
}

const NodeDetailContext = createContext<NodeDetailContextValue | null>(null);

export function useNodeDetail() {
  const ctx = useContext(NodeDetailContext);
  if (!ctx) throw new Error('useNodeDetail must be used within NodeDetailProvider');
  return ctx;
}

export function NodeDetailProvider({ children }: { children: React.ReactNode }) {
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [parentLabel, setParentLabel] = useState<string | null>(null);
  const [openSeq, setOpenSeq] = useState(0);
  const location = useLocation();

  const openNodeDetail = useCallback((id: string, label?: string) => {
    setNodeId(id);
    setParentLabel(label ?? null);
    setOpenSeq(nextModalSeq());
  }, []);

  const closeNodeDetail = useCallback(() => {
    setNodeId(null);
    setParentLabel(null);
  }, []);

  // Close modal on route change
  useEffect(() => {
    setNodeId(null);
    setParentLabel(null);
  }, [location.pathname]);

  return (
    <NodeDetailContext.Provider value={{ openNodeDetail, nodeDetailId: nodeId, nodeParentLabel: parentLabel, closeNodeDetail, nodeOpenSeq: openSeq }}>
      {children}
    </NodeDetailContext.Provider>
  );
}
