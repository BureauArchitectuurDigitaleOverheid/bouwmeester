import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { CurrentPersonProvider } from '@/contexts/CurrentPersonContext';
import { VocabularyProvider } from '@/contexts/VocabularyContext';
import { TaskDetailProvider } from '@/contexts/TaskDetailContext';
import { NodeDetailProvider } from '@/contexts/NodeDetailContext';
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
import { LoginPage } from '@/pages/LoginPage';

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
  const { loading, authenticated, oidcConfigured } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-text-secondary">Laden...</div>
      </div>
    );
  }

  // If OIDC is configured and user is not authenticated, show login
  if (oidcConfigured && !authenticated) {
    return <LoginPage />;
  }

  // No OIDC configured (local dev) or authenticated — continue
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate>
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
                  </Route>
                </Routes>
                <DetailModals />
              </NodeDetailProvider>
              </TaskDetailProvider>
            </BrowserRouter>
            </VocabularyProvider>
          </CurrentPersonProvider>
        </AuthGate>
      </AuthProvider>
    </QueryClientProvider>
  );
}
