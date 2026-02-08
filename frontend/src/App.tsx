import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CurrentPersonProvider } from '@/contexts/CurrentPersonContext';
import { VocabularyProvider } from '@/contexts/VocabularyContext';
import { AppLayout } from '@/components/layout/AppLayout';
import { InboxPage } from '@/pages/InboxPage';
import { CorpusPage } from '@/pages/CorpusPage';
import { NodeDetailPage } from '@/pages/NodeDetailPage';
import { TasksPage } from '@/pages/TasksPage';
import { PeoplePage } from '@/pages/PeoplePage';
import { OrganisatiePage } from '@/pages/OrganisatiePage';
import { SearchPage } from '@/pages/SearchPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <CurrentPersonProvider>
        <VocabularyProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<InboxPage />} />
              <Route path="/corpus" element={<CorpusPage />} />
              <Route path="/nodes/:id" element={<NodeDetailPage />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/people" element={<PeoplePage />} />
              <Route path="/organisatie" element={<OrganisatiePage />} />
              <Route path="/search" element={<SearchPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
        </VocabularyProvider>
      </CurrentPersonProvider>
    </QueryClientProvider>
  );
}
