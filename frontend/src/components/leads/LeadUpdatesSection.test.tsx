import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@/contexts/ToastContext';
import { LeadUpdatesSection } from './LeadUpdatesSection';
import type { LeadUpdatePost } from '@/types';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// A concept with a public text: publishing it puts that text on the page.
const POST = {
  id: 'p1',
  lead_id: 'l1',
  titel: 'Concept',
  body_internal: null,
  body_public: 'Openbare tekst',
  published_at: null,
  created_at: '2026-01-02T00:00:00Z',
} as unknown as LeadUpdatePost;

/** The lead is writable; `initiatief:update` answers `mayPublish`. */
function backend(mayPublish: boolean) {
  mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const json = (data: unknown) =>
      new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/api/authz/evaluations')) {
      const body = JSON.parse(String(init?.body)) as { evaluations: { action: string }[] };
      return json({
        evaluations: body.evaluations.map((e) => ({
          decision: e.action === 'initiatief:update' ? mayPublish : true,
        })),
      });
    }
    if (url.includes('/updates')) return json([POST]);
    return json([]);
  });
}

function renderSection(initiatiefId: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <LeadUpdatesSection leadId="l1" initiatiefId={initiatiefId} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const PUBLIC_BODY = 'Publieke samenvatting (community-pagina)';

const byLabel = (container: HTMLElement, label: string) =>
  container.querySelector(`[text="${label}"], [accessible-label="${label}"], [label="${label}"]`);

/** Wait for the write controls, then open the composer. */
async function compose(container: HTMLElement) {
  await waitFor(() => expect(byLabel(container, 'Bewerken')).not.toBeNull());
  fireEvent.click(byLabel(container, 'Nieuwe update')!);
  await waitFor(() => expect(byLabel(container, 'Opslaan als concept')).not.toBeNull());
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe('LeadUpdatesSection public controls', () => {
  it('hides them from who may update the lead but not the initiatief', async () => {
    backend(false);
    const { container } = renderSection('i1');
    await compose(container);

    expect(byLabel(container, 'Publiceren')).toBeNull();
    expect(byLabel(container, PUBLIC_BODY)).toBeNull();
    // Publishing an update without a public text stays with the lead.
    expect(byLabel(container, 'Direct publiceren')).not.toBeNull();
  });

  it('shows them to who may update the initiatief', async () => {
    backend(true);
    const { container } = renderSection('i1');
    await compose(container);

    await waitFor(() => expect(byLabel(container, 'Publiceren')).not.toBeNull());
    expect(byLabel(container, PUBLIC_BODY)).not.toBeNull();
  });

  it('shows them on a lead without initiatief: it shows on no page', async () => {
    backend(false);
    const { container } = renderSection(null);
    await compose(container);

    expect(byLabel(container, 'Publiceren')).not.toBeNull();
    expect(byLabel(container, PUBLIC_BODY)).not.toBeNull();
  });
});
