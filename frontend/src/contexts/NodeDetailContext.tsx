import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

interface NodeDetailContextValue {
  openNodeDetail: (nodeId: string) => void;
  nodeDetailId: string | null;
  closeNodeDetail: () => void;
}

const NodeDetailContext = createContext<NodeDetailContextValue | null>(null);

export function useNodeDetail() {
  const ctx = useContext(NodeDetailContext);
  if (!ctx) throw new Error('useNodeDetail must be used within NodeDetailProvider');
  return ctx;
}

export function NodeDetailProvider({ children }: { children: React.ReactNode }) {
  const [nodeId, setNodeId] = useState<string | null>(null);
  const location = useLocation();

  const openNodeDetail = useCallback((id: string) => {
    setNodeId(id);
  }, []);

  const closeNodeDetail = useCallback(() => {
    setNodeId(null);
  }, []);

  // Close modal on route change
  useEffect(() => {
    setNodeId(null);
  }, [location.pathname]);

  return (
    <NodeDetailContext.Provider value={{ openNodeDetail, nodeDetailId: nodeId, closeNodeDetail }}>
      {children}
    </NodeDetailContext.Provider>
  );
}
