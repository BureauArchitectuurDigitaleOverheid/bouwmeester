import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@/contexts/ToastContext';
import { InitiatiefMensen } from './InitiatiefMensen';
import type { InitiatiefDetail } from '@/types';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const member = (person_id: string, person_naam: string, rol: string) => ({
  initiatief_id: 'i1',
  person_id,
  person_naam,
  rol,
  created_at: '2026-01-01T00:00:00Z',
});

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
  members: [member('p1', 'Ann', 'eigenaar'), member('p2', 'Bea', 'contributor')],
  eenheden: [],
};

interface Question {
  action: string;
  resource: { type: string; id?: string; properties?: Record<string, unknown> };
}

/** The backend allows only removing Bea; everything else is refused. */
function backend() {
  mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const json = (data: unknown) =>
      new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/api/authz/evaluations')) {
      const body = JSON.parse(String(init?.body)) as { evaluations: Question[] };
      return json({
        evaluations: body.evaluations.map((e) => ({
          decision: e.action === 'resource_role:revoke' && e.resource.properties?.target_person_id === 'p2',
        })),
      });
    }
    return json([]);
  });
}

function askedQuestions(): Question[] {
  return mockFetch.mock.calls
    .filter(([url]) => String(url).includes('/api/authz/evaluations'))
    .flatMap(([, init]) => (JSON.parse(String((init as RequestInit).body)) as { evaluations: Question[] }).evaluations);
}

function renderMensen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <InitiatiefMensen initiatief={INITIATIEF} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const byLabel = (container: HTMLElement, label: string) => container.querySelector(`[accessible-label="${label}"]`);

beforeEach(() => {
  mockFetch.mockReset();
});

describe('InitiatiefMensen member removal', () => {
  it('asks the backend a revoke question per member', async () => {
    backend();
    renderMensen();

    await waitFor(() =>
      expect(askedQuestions().filter((q) => q.action === 'resource_role:revoke')).toHaveLength(2),
    );
    expect(askedQuestions()).toContainEqual({
      action: 'resource_role:revoke',
      resource: { type: 'initiatief', id: 'i1', properties: { rol: 'eigenaar', target_person_id: 'p1' } },
    });
  });

  it('shows the remove button only where the backend allows the revoke', async () => {
    backend();
    const { container } = renderMensen();

    await waitFor(() => expect(byLabel(container, 'Bea verwijderen')).not.toBeNull());
    // Ann is the last eigenaar: the backend says no, so no button.
    expect(byLabel(container, 'Ann verwijderen')).toBeNull();
  });
});
