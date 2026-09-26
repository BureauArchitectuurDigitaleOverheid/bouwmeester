import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuditLogPage } from './AuditLogPage';
import { Sidebar } from '@/components/layout/Sidebar';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// audit:read held through a role on an eenheid, and whether a system role
// grants it too. Only the latter opens the tenant-wide feed.
const rights = { scoped: true, system: false };

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    hasPermission: (perm: string) => perm === 'audit:read' && rights.scoped,
    hasAnyPermission: () => false,
    hasSystemPermission: (perm: string) => perm === 'audit:read' && rights.system,
    managesEenheid: () => false,
    isSuperAdmin: false,
  }),
}));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    person: { id: 'p1', managed_eenheden: [] },
    oidcConfigured: true,
    loading: false,
    authenticated: true,
    logout: () => {},
  }),
}));
vi.mock('@/contexts/CurrentPersonContext', () => ({
  useCurrentPerson: () => ({ currentPerson: { id: 'p1' } }),
}));
vi.mock('@/contexts/NodeDetailContext', () => ({ useNodeDetail: () => ({ openNodeDetail: () => {} }) }));
vi.mock('@/contexts/TaskDetailContext', () => ({ useTaskDetail: () => ({ openTaskDetail: () => {} }) }));

function renderAt(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/auditlog']}>
        <Routes>
          <Route path="/auditlog" element={ui} />
          <Route path="/" element={<div data-testid="home" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const feedRequested = () => mockFetch.mock.calls.some(([url]) => String(url).includes('/api/activity/feed'));
const auditNavItem = (container: HTMLElement) => container.querySelector('[text="Auditlog"]');

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockImplementation(
    async () =>
      new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
});

describe('audit log visibility', () => {
  it('hides the nav item and the page for audit:read from a scoped role only', async () => {
    rights.system = false;
    const sidebar = renderAt(<Sidebar />);
    expect(auditNavItem(sidebar.container)).toBeNull();
    sidebar.unmount();

    const page = renderAt(<AuditLogPage />);
    await waitFor(() => expect(page.getByTestId('home')).toBeTruthy());
    expect(feedRequested()).toBe(false);
  });

  it('shows the nav item and loads the feed for audit:read from a system role', async () => {
    rights.system = true;
    const sidebar = renderAt(<Sidebar />);
    expect(auditNavItem(sidebar.container)).not.toBeNull();
    sidebar.unmount();

    const page = renderAt(<AuditLogPage />);
    await waitFor(() => expect(feedRequested()).toBe(true));
    expect(page.queryByTestId('home')).toBeNull();
  });
});
