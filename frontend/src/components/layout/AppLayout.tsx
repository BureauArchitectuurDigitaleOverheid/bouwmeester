import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useUIStore } from '@/store/ui';
import { useIsMobile } from '@/hooks/useMediaQuery';

export function AppLayout() {
  const isMobile = useIsMobile();
  const { mobileSidebarOpen, setMobileSidebarOpen } = useUIStore();

  // Close mobile sidebar on Escape
  useEffect(() => {
    if (!mobileSidebarOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileSidebarOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mobileSidebarOpen, setMobileSidebarOpen]);

  return (
    <div className="flex min-h-screen bg-background">
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

      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 p-4 md:p-6 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
