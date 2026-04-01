import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Clock, XCircle } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { ChatToggleButton } from '@/components/chat/ChatToggleButton';
import { SearchModal } from '@/components/search/SearchModal';
import { useUIStore } from '@/store/ui';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { useAuth } from '@/contexts/AuthContext';
import { OnboardingModal } from '@/components/onboarding/OnboardingModal';
import { GlobalDropOverlay } from '@/components/common/GlobalDropOverlay';
import { FileActionChooser } from '@/components/common/FileActionChooser';
import { useGlobalFileDropContext } from '@/hooks/useGlobalFileDropContext';

function PlacementBanner() {
  const { person } = useAuth();
  const [showReRequest, setShowReRequest] = useState(false);

  if (!person?.needs_placement) return null;

  // User's last request was denied — show re-request option
  if (person.placement_denied) {
    return (
      <>
        <div className="bg-red-50 border-b border-red-200 px-4 py-2.5 flex items-center justify-center gap-2 text-sm text-red-800">
          <XCircle className="h-4 w-4 shrink-0" />
          <span>Je teamverzoek is afgewezen.</span>
          <button
            onClick={() => setShowReRequest(true)}
            className="underline font-medium hover:text-red-900"
          >
            Opnieuw aanvragen
          </button>
        </div>
        {showReRequest && <OnboardingModal />}
      </>
    );
  }

  // User has a pending request
  if (person.has_pending_placement) {
    return (
      <div className="bg-amber-50 border-b border-amber-200 px-4 py-2.5 flex items-center justify-center gap-2 text-sm text-amber-800">
        <Clock className="h-4 w-4 shrink-0" />
        <span>Je teamverzoek wordt beoordeeld door een manager.</span>
      </div>
    );
  }

  return null;
}

export function AppLayout() {
  const isMobile = useIsMobile();
  const location = useLocation();
  const { mobileSidebarOpen, setMobileSidebarOpen, chatOpen, chatWidth, searchModalOpen, setSearchModalOpen } = useUIStore();
  const { isDragging } = useGlobalFileDropContext();

  // Close mobile sidebar on Escape
  useEffect(() => {
    if (!mobileSidebarOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileSidebarOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mobileSidebarOpen, setMobileSidebarOpen]);

  // Global "/" shortcut to open search modal (unless on /search page)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        !(document.activeElement instanceof HTMLInputElement) &&
        !(document.activeElement instanceof HTMLTextAreaElement) &&
        !(document.activeElement as HTMLElement)?.isContentEditable
      ) {
        // On /search page, the page handles "/" itself (focuses input)
        if (location.pathname === '/search') return;
        e.preventDefault();
        setSearchModalOpen(true);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [location.pathname, setSearchModalOpen]);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Desktop sidebar */}
      {!isMobile && <Sidebar />}

      {/* Mobile sidebar overlay */}
      {isMobile && mobileSidebarOpen && (
        <>
          <div
            className="fixed inset-0 bg-black/40 z-40"
            onClick={() => setMobileSidebarOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 z-50 w-72">
            <Sidebar mobile />
          </div>
        </>
      )}

      <div
        className="flex flex-col flex-1 min-w-0 transition-all duration-300"
        style={{ marginRight: chatOpen && !isMobile ? chatWidth : 0 }}
      >
        <Header />
        <PlacementBanner />
        <main className="flex-1 p-4 md:p-6 overflow-y-auto" style={{ scrollbarGutter: 'stable' }}>
          <Outlet />
        </main>
      </div>
      <ChatPanel />
      <ChatToggleButton />
      <SearchModal open={searchModalOpen} onClose={() => setSearchModalOpen(false)} />
      <GlobalDropOverlay visible={isDragging} />
      <FileActionChooser />
    </div>
  );
}
