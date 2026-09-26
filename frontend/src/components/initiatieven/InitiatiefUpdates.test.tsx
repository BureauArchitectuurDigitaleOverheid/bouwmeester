import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@/contexts/ToastContext';
import { InitiatiefUpdates } from './InitiatiefUpdates';
import type { InitiatiefDetail, InitiatiefUpdatePost } from '@/types';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const INITIATIEF: InitiatiefDetail = {
  id: 'i1',
  naam: 'Regelrecht',
  slug: null,
  beschrijving: null,
  kleur: null,
  funnel_enabled: false,
  public_page_enabled: false,
  score_strategisch_label: null,
  score_politiek_label: null,
  score_positie_label: null,
  created_by_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
  members: [],
  eenheden: [],
  access_level: 'eigenaar',
};

const POST = {
  id: 'p1',
  initiatief_id: 'i1',
  titel: 'Eerste update',
  body: null,
  published_at: null,
  created_at: '2026-01-02T00:00:00Z',
} as unknown as InitiatiefUpdatePost;

/** The backend answers `decision` to every question; the updates list holds one draft. */
function backend(decision: boolean) {
  mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const json = (data: unknown) =>
      new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/api/authz/evaluations')) {
      const body = JSON.parse(String(init?.body)) as { evaluations: unknown[] };
      return json({ evaluations: body.evaluations.map(() => ({ decision })) });
    }
    if (url.includes('/updates')) return json([POST]);
    return json([]);
  });
}

function renderUpdates() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <InitiatiefUpdates initiatief={INITIATIEF} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const byLabel = (container: HTMLElement, label: string) =>
  container.querySelector(`[text="${label}"], [accessible-label="${label}"]`);

beforeEach(() => {
  mockFetch.mockReset();
});

describe('InitiatiefUpdates write controls', () => {
  it('hides them when the backend says no, even for an eigenaar in access_level', async () => {
    backend(false);
    const { container } = renderUpdates();

    await waitFor(() => expect(container.textContent).toContain('Updates (1)'));
    await waitFor(() =>
      expect(mockFetch.mock.calls.some(([url]) => String(url).includes('/api/authz/evaluations'))).toBe(true),
    );

    expect(byLabel(container, 'Nieuwe update')).toBeNull();
    expect(byLabel(container, 'Bewerken')).toBeNull();
  });

  it('shows them when the backend says yes', async () => {
    backend(true);
    const { container } = renderUpdates();

    await waitFor(() => expect(byLabel(container, 'Nieuwe update')).not.toBeNull());
    await waitFor(() => expect(byLabel(container, 'Bewerken')).not.toBeNull());
  });
});
