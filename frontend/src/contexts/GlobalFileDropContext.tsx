import { createContext, useState, useCallback, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useGlobalFileDrop } from '@/hooks/useGlobalFileDrop';
import { isEmailFile } from '@/utils/emailParser';
import { INITIATIEVEN_PATH, isLeadDropPath } from '@/utils/initiatiefRoutes';
import { useToast } from '@/contexts/ToastContext';

type FileSubscriber = (files: File[]) => void;

interface GlobalFileDropContextType {
  isDragging: boolean;
  showChooser: boolean;
  setShowChooser: (show: boolean) => void;
  chooseAction: (action: 'lead' | 'bron') => void;
  /** Subscribe to file drops for the current page. Returns unsubscribe fn. */
  subscribe: (cb: FileSubscriber) => () => void;
  /** Files shown in the chooser dialog (only used by FileActionChooser). */
  chooserFiles: File[];
  discardChooserFiles: () => void;
}

const GlobalFileDropContext = createContext<GlobalFileDropContextType | null>(null);

export function GlobalFileDropProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { showWarning } = useToast();
  const [showChooser, setShowChooser] = useState(false);
  const [chooserFiles, setChooserFiles] = useState<File[]>([]);
  const locationRef = useRef(location);
  locationRef.current = location;

  // Subscribers: page-level components register to receive files directly
  const subscribersRef = useRef<Set<FileSubscriber>>(new Set());
  // Files held for delivery after navigation (chooser -> navigate -> page mounts -> subscribes)
  const deferredFilesRef = useRef<File[] | null>(null);

  const subscribe = useCallback((cb: FileSubscriber) => {
    subscribersRef.current.add(cb);
    // Deliver any deferred files from a chooser navigation
    if (deferredFilesRef.current) {
      const files = deferredFilesRef.current;
      deferredFilesRef.current = null;
      cb(files);
    }
    return () => { subscribersRef.current.delete(cb); };
  }, []);

  const handleFiles = useCallback((files: File[]) => {
    const pathname = locationRef.current.pathname;
    const isContextPage = isLeadDropPath(pathname) || pathname.startsWith('/corpus') || pathname.startsWith('/nodes/');

    // Email files (.eml/.msg) always route to leads, regardless of current page
    const hasEmail = files.some(isEmailFile);
    if (hasEmail && !isLeadDropPath(pathname)) {
      deferredFilesRef.current = files;
      navigate(INITIATIEVEN_PATH);
      return;
    }

    if (isContextPage && subscribersRef.current.size > 0) {
      subscribersRef.current.forEach(cb => cb(files));
    } else if (!isContextPage) {
      setChooserFiles(files);
      setShowChooser(true);
    }
  }, [navigate]);

  const handleEmptyFileDrop = useCallback(() => {
    showWarning(
      'Je Outlook-versie ondersteunt geen directe e-mail drag-and-drop naar de browser. '
      + 'Sleep de e-mail eerst naar je bureaublad en sleep het .eml-bestand dan hierheen.'
    );
  }, [showWarning]);

  const discardChooserFiles = useCallback(() => {
    setChooserFiles([]);
  }, []);

  const chooseAction = useCallback((action: 'lead' | 'bron') => {
    const files = chooserFiles;
    setShowChooser(false);
    setChooserFiles([]);
    // Store files for delivery after the target page mounts and subscribes
    deferredFilesRef.current = files;
    navigate(action === 'lead' ? INITIATIEVEN_PATH : '/corpus');
  }, [navigate, chooserFiles]);

  const { isDragging } = useGlobalFileDrop({
    onFiles: handleFiles,
    onEmptyFileDrop: handleEmptyFileDrop,
  });

  return (
    <GlobalFileDropContext.Provider
      value={{
        isDragging,
        showChooser,
        setShowChooser,
        chooseAction,
        subscribe,
        chooserFiles,
        discardChooserFiles,
      }}
    >
      {children}
    </GlobalFileDropContext.Provider>
  );
}

export { GlobalFileDropContext };
