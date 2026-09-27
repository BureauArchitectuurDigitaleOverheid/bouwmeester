import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@/contexts/ToastContext';
import { LeadDetailPanel } from './LeadDetailPanel';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const LEAD = {
  id: 'l1',
  title: 'Lead',
  description: null,
  organization: null,
  organisatie_eenheid_id: null,
  organisatie_eenheid: null,
  stage: 'verkennen',
  assignee_id: null,
  assignee: null,
  brought_by_id: null,
  brought_by: null,
  initiatief_id: 'i1',
  initiatief: null,
  next_action: null,
  next_action_date: null,
  tags: [],
  sort_order: 0,
  raw_intake_text: null,
  engagement_type: null,
  score_strategisch: null,
  score_politiek: null,
  score_positie: null,
  public_visible: false,
  public_title: null,
  public_summary: null,
  attachment_count: 0,
  contact_names: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
  activities: [],
  attachments: [],
  contacts: [],
  linked_nodes: [],
  github_links: [],
};

const INITIATIEF = { id: 'i1', naam: 'Regelrecht', slug: 'rr', public_page_enabled: true };

/** `lead:update` holds; `initiatief:update` answers `mayPublish`. */
function backend(mayPublish: boolean) {
  mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const json = (data: unknown) =>
      new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
    const path = String(url);
    if (path.includes('/api/authz/evaluations')) {
      const body = JSON.parse(String(init?.body)) as { evaluations: { action: string }[] };
      return json({
        evaluations: body.evaluations.map((e) => ({
          decision: e.action === 'initiatief:update' ? mayPublish : true,
        })),
      });
    }
    if (/\/api\/leads\/l1(\?|$)/.test(path)) return json(LEAD);
    if (/\/api\/initiatieven(\?|$)/.test(path)) return json([INITIATIEF]);
    return json([]);
  });
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <LeadDetailPanel leadId="l1" open onClose={() => {}} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const byLabel = (container: ParentNode, label: string) =>
  container.querySelector(`[text="${label}"], [label="${label}"]`);

/** Open the edit form once `lead:update` has been decided. */
async function edit() {
  const { baseElement } = renderPanel();
  await waitFor(() => expect(byLabel(baseElement, 'Bewerken')?.hasAttribute('disabled')).toBe(false));
  fireEvent.click(byLabel(baseElement, 'Bewerken')!);
  await waitFor(() => expect(byLabel(baseElement, 'Engagement type') ?? byLabel(baseElement, 'Titel')).not.toBeNull());
  return baseElement;
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe('LeadDetailPanel public fields', () => {
  it('are not offered to who may update the lead but not the initiatief', async () => {
    backend(false);
    const page = await edit();
    await waitFor(() =>
      expect(mockFetch.mock.calls.some(([, init]) => String(init?.body).includes('initiatief:update'))).toBe(true),
    );
    expect(byLabel(page, 'Publiek tonen')).toBeNull();
    expect(byLabel(page, 'Publieke titel')).toBeNull();
  });

  it('are offered to who may update the initiatief', async () => {
    backend(true);
    const page = await edit();
    await waitFor(() => expect(byLabel(page, 'Publiek tonen')).not.toBeNull());
    expect(byLabel(page, 'Publieke titel')).not.toBeNull();
  });
});
