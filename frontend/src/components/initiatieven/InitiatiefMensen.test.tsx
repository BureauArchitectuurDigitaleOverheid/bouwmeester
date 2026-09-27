import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@/contexts/ToastContext';
import { InitiatiefMensen } from './InitiatiefMensen';
import type { InitiatiefDetail } from '@/types';
import { askedQuestions as askedQuestionsOf, fakeBackend } from '@/test/authzBackend';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const member = (person_id: string, person_naam: string, rol: string) => ({
  initiatief_id: 'i1',
  person_id,
  person_naam,
  rol,
  created_at: '2026-01-01T00:00:00Z',
});

const eenheid = (eenheid_id: string, eenheid_naam: string, rol: string) => ({
  initiatief_id: 'i1',
  eenheid_id,
  eenheid_naam,
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

/** The backend allows only removing Bea; everything else is refused. */
function backend() {
  fakeBackend(mockFetch, {
    decide: (q) => q.action === 'resource_role:revoke' && q.resource.properties?.target_person_id === 'p2',
  });
}

const askedQuestions = () => askedQuestionsOf(mockFetch);

function renderMensen(initiatief: InitiatiefDetail = INITIATIEF) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <InitiatiefMensen initiatief={initiatief} />
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

describe('InitiatiefMensen eenheid grants', () => {
  const WITH_EENHEDEN: InitiatiefDetail = {
    ...INITIATIEF,
    eenheden: [eenheid('e1', 'Team Recht', 'viewer'), eenheid('e2', 'Team Data', 'contributor')],
  };

  // Authority over Team Recht's grant, up to contributor; none over Team Data.
  function eenheidBackend() {
    fakeBackend(mockFetch, {
      decide: ({ action, resource }) => {
        const target = resource.properties?.target_eenheid_id;
        if (action === 'resource_role:revoke') return target === 'e1';
        if (action === 'resource_role:grant') return target === 'e1' && resource.properties?.rol !== 'eigenaar';
        return false;
      },
    });
  }

  const rolSelects = (container: HTMLElement) =>
    Array.from(container.querySelectorAll<HTMLSelectElement>('select[aria-label="Rol van deze eenheid"]'));

  it('asks revoke and grant with the eenheid as target', async () => {
    eenheidBackend();
    renderMensen(WITH_EENHEDEN);

    await waitFor(() =>
      expect(askedQuestions()).toContainEqual({
        action: 'resource_role:revoke',
        resource: { type: 'initiatief', id: 'i1', properties: { rol: 'viewer', target_eenheid_id: 'e1' } },
      }),
    );
    expect(askedQuestions()).toContainEqual({
      action: 'resource_role:grant',
      resource: { type: 'initiatief', id: 'i1', properties: { rol: 'contributor', target_eenheid_id: 'e1' } },
    });
  });

  it('offers remove and only the grantable rols where the backend allows them', async () => {
    eenheidBackend();
    const { container } = renderMensen(WITH_EENHEDEN);

    await waitFor(() => expect(byLabel(container, 'Team Recht verwijderen')).not.toBeNull());
    expect(byLabel(container, 'Team Data verwijderen')).toBeNull();

    // One select, for Team Recht, without eigenaar; Team Data shows a tag.
    await waitFor(() => expect(rolSelects(container)).toHaveLength(1));
    expect(Array.from(rolSelects(container)[0].options).map((o) => o.value)).toEqual(['contributor', 'viewer']);
    expect(container.querySelector('nldd-tag[text="Bijdrager"]')).not.toBeNull();
  });
});

describe('InitiatiefMensen member rol changes', () => {
  const buttons = (container: HTMLElement, text: string) => container.querySelectorAll(`nldd-button[text="${text}"]`);

  // Ann is the only eigenaar member, but Team Recht is eigenaar too: the
  // backend counts that, so revoking Ann's eigenaar is allowed.
  const WITH_EIGENAAR_EENHEID: InitiatiefDetail = {
    ...INITIATIEF,
    eenheden: [eenheid('e1', 'Team Recht', 'eigenaar')],
  };

  it('asks the grant of the new rol per member', async () => {
    fakeBackend(mockFetch, { decide: () => false });
    renderMensen();

    await waitFor(() =>
      expect(askedQuestions()).toContainEqual({
        action: 'resource_role:grant',
        resource: { type: 'initiatief', id: 'i1', properties: { rol: 'contributor', target_person_id: 'p1' } },
      }),
    );
    expect(askedQuestions()).toContainEqual({
      action: 'resource_role:grant',
      resource: { type: 'initiatief', id: 'i1', properties: { rol: 'eigenaar', target_person_id: 'p2' } },
    });
  });

  it('offers "Maak bijdrager" to the only eigenaar member when the backend allows the revoke', async () => {
    fakeBackend(mockFetch, {
      decide: ({ action, resource }) =>
        resource.properties?.target_person_id === 'p1' &&
        (action === 'resource_role:revoke' || resource.properties?.rol === 'contributor'),
    });
    const { container } = renderMensen(WITH_EIGENAAR_EENHEID);

    await waitFor(() => expect(buttons(container, 'Maak bijdrager')).toHaveLength(1));
    expect(buttons(container, 'Maak eigenaar')).toHaveLength(0);
  });

  it('offers no rol change when the revoke is refused, even with the grant', async () => {
    fakeBackend(mockFetch, { decide: ({ action }) => action === 'resource_role:grant' });
    const { container } = renderMensen();

    // The add control rides in the same batch: once it shows, all decisions landed.
    await waitFor(() => expect(container.querySelector('[placeholder="Lid toevoegen..."]')).not.toBeNull());
    expect(buttons(container, 'Maak bijdrager')).toHaveLength(0);
    expect(buttons(container, 'Maak eigenaar')).toHaveLength(0);
  });
});
