import { createContext, useContext, useState, useCallback, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useGlobalFileDrop } from '@/hooks/useGlobalFileDrop';

interface GlobalFileDropContextType {
  isDragging: boolean;
  pendingFiles: File[];
  clearPendingFiles: () => void;
  showChooser: boolean;
  setShowChooser: (show: boolean) => void;
  chooseAction: (action: 'lead' | 'bron') => void;
}

const GlobalFileDropContext = createContext<GlobalFileDropContextType | null>(null);

export function GlobalFileDropProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [showChooser, setShowChooser] = useState(false);
  const locationRef = useRef(location);
  locationRef.current = location;

  const handleFiles = useCallback((files: File[]) => {
    const pathname = locationRef.current.pathname;

    setPendingFiles(files);

    if (pathname.startsWith('/leads')) {
      // LeadsPage will pick up pendingFiles
    } else if (pathname.startsWith('/corpus') || pathname.startsWith('/nodes/')) {
      // CorpusPage will pick up pendingFiles
    } else {
      setShowChooser(true);
    }
  }, []);

  const clearPendingFiles = useCallback(() => {
    setPendingFiles([]);
  }, []);

  const chooseAction = useCallback((action: 'lead' | 'bron') => {
    setShowChooser(false);
    if (action === 'lead') {
      navigate('/leads');
      // pendingFiles stay in state — LeadsPage picks them up after mount
    } else {
      navigate('/corpus');
      // pendingFiles stay in state — CorpusPage picks them up after mount
    }
  }, [navigate]);

  const { isDragging } = useGlobalFileDrop({ onFiles: handleFiles });

  return (
    <GlobalFileDropContext.Provider
      value={{
        isDragging,
        pendingFiles,
        clearPendingFiles,
        showChooser,
        setShowChooser,
        chooseAction,
      }}
    >
      {children}
    </GlobalFileDropContext.Provider>
  );
}

export function useGlobalFileDropContext() {
  const ctx = useContext(GlobalFileDropContext);
  if (!ctx) throw new Error('useGlobalFileDropContext must be used within GlobalFileDropProvider');
  return ctx;
}
