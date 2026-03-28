import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Clock } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { ChatToggleButton } from '@/components/chat/ChatToggleButton';
import { SearchModal } from '@/components/search/SearchModal';
import { useUIStore } from '@/store/ui';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { useAuth } from '@/contexts/AuthContext';

function PendingPlacementBanner() {
  const { person } = useAuth();
  if (!person?.needs_placement || !person?.has_pending_placement) return null;
  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-2.5 flex items-center justify-center gap-2 text-sm text-amber-800">
      <Clock className="h-4 w-4 shrink-0" />
      <span>Je plaatsingsverzoek wordt beoordeeld door een manager.</span>
    </div>
  );
}

export function AppLayout() {
  const isMobile = useIsMobile();
  const location = useLocation();
  const { mobileSidebarOpen, setMobileSidebarOpen, chatOpen, chatWidth, searchModalOpen, setSearchModalOpen } = useUIStore();

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
        <PendingPlacementBanner />
        <main className="flex-1 p-4 md:p-6 overflow-y-auto" style={{ scrollbarGutter: 'stable' }}>
          <Outlet />
        </main>
      </div>
      <ChatPanel />
      <ChatToggleButton />
      <SearchModal open={searchModalOpen} onClose={() => setSearchModalOpen(false)} />
    </div>
  );
}
