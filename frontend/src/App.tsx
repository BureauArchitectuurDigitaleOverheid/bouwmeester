import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { CurrentPersonProvider } from '@/contexts/CurrentPersonContext';
import { VocabularyProvider } from '@/contexts/VocabularyContext';
import { TaskDetailProvider } from '@/contexts/TaskDetailContext';
import { NodeDetailProvider } from '@/contexts/NodeDetailContext';
import { ToastProvider } from '@/contexts/ToastContext';
import { DetailModals } from '@/components/common/DetailModals';
import { AppLayout } from '@/components/layout/AppLayout';
import { InboxPage } from '@/pages/InboxPage';
import { CorpusPage } from '@/pages/CorpusPage';
import { NodeDetailPage } from '@/pages/NodeDetailPage';
import { TasksPage } from '@/pages/TasksPage';
import { PeoplePage } from '@/pages/PeoplePage';
import { OrganisatiePage } from '@/pages/OrganisatiePage';
import { SearchPage } from '@/pages/SearchPage';
import { ParlementairPage } from '@/pages/ParlementairPage';
import { EenheidOverzichtPage } from '@/pages/EenheidOverzichtPage';
import { AdminPage } from '@/pages/AdminPage';
import { AuditLogPage } from '@/pages/AuditLogPage';
import { OnboardingModal } from '@/components/onboarding/OnboardingModal';
import { LoginPage } from '@/pages/LoginPage';
import { AccessDeniedPage } from '@/pages/AccessDeniedPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AuthGate({ children }: { children: React.ReactNode }) {
  const { loading, authenticated, oidcConfigured, error, accessDenied, deniedEmail } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-text-secondary">Laden...</div>
      </div>
    );
  }

  // Show error state when auth status check failed
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-sm w-full space-y-4 text-center">
          <h1 className="text-xl font-semibold text-text">Verbindingsfout</h1>
          <p className="text-sm text-text-secondary">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 rounded-lg border border-border text-sm hover:bg-gray-100 transition-colors"
          >
            Opnieuw proberen
          </button>
        </div>
      </div>
    );
  }

  // If access was denied by the whitelist, show access denied page
  if (accessDenied) {
    return <AccessDeniedPage email={deniedEmail} />;
  }

  // If OIDC is configured and user is not authenticated, show login
  if (oidcConfigured && !authenticated) {
    return <LoginPage />;
  }

  // No OIDC configured (local dev) or authenticated — continue
  return <>{children}</>;
}

function OnboardingGate({ children }: { children: React.ReactNode }) {
  const { oidcConfigured, authenticated, person } = useAuth();

  if (oidcConfigured && authenticated && person?.needs_onboarding) {
    return <OnboardingModal />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
      <AuthProvider>
        <AuthGate>
          <OnboardingGate>
          <CurrentPersonProvider>
            <VocabularyProvider>
            <BrowserRouter>
              <TaskDetailProvider>
              <NodeDetailProvider>
                <Routes>
                  <Route element={<AppLayout />}>
                    <Route path="/" element={<InboxPage />} />
                    <Route path="/corpus" element={<CorpusPage />} />
                    <Route path="/nodes/:id" element={<NodeDetailPage />} />
                    <Route path="/tasks" element={<TasksPage />} />
                    <Route path="/people" element={<PeoplePage />} />
                    <Route path="/organisatie" element={<OrganisatiePage />} />
                    <Route path="/eenheid-overzicht" element={<EenheidOverzichtPage />} />
                    <Route path="/search" element={<SearchPage />} />
                    <Route path="/parlementair" element={<ParlementairPage />} />
                    <Route path="/admin" element={<AdminPage />} />
                    <Route path="/auditlog" element={<AuditLogPage />} />
                  </Route>
                </Routes>
                <DetailModals />
              </NodeDetailProvider>
              </TaskDetailProvider>
            </BrowserRouter>
            </VocabularyProvider>
          </CurrentPersonProvider>
          </OnboardingGate>
        </AuthGate>
      </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
