import { describe, it, expect, vi, beforeEach } from 'vitest';
import { waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { askedQuestions, fakeBackend } from '@/test/authzBackend';
import { OrganisatieDetail } from './OrganisatieDetail';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ isSuperAdmin: false }),
}));

const EENHEID = { id: 'e1', naam: 'Team Recht', type: 'team', parent_id: null, manager: null };

// May dissolve the eenheid, may not edit it.
beforeEach(() => {
  mockFetch.mockReset();
  fakeBackend(mockFetch, {
    decide: (q) => q.action === 'eenheid:dissolve',
    get: (url) => (url.includes('/personen') ? { eenheid: EENHEID, personen: [], children: [] } : EENHEID),
  });
});

const noop = () => {};

function renderDetail() {
  return renderWithProviders(
    <OrganisatieDetail
      selectedId="e1"
      onEdit={noop}
      onDelete={noop}
      onAddChild={noop}
      onAddPerson={noop}
      onAddAgent={noop}
      onEditPerson={noop}
    />,
  );
}

describe('OrganisatieDetail delete button', () => {
  it('asks eenheid:dissolve, the rule DELETE follows', async () => {
    renderDetail();

    await waitFor(() =>
      expect(askedQuestions(mockFetch)).toContainEqual({
        action: 'eenheid:dissolve',
        resource: { type: 'organisatie_eenheid', id: 'e1' },
      }),
    );
  });

  it('shows delete on dissolve alone, without the edit button', async () => {
    const { container } = renderDetail();

    await waitFor(() => expect(container.querySelector('nldd-button[text="Verwijderen"]')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Verwijderen"]')?.hasAttribute('disabled')).toBe(false);
    expect(container.querySelector('nldd-button[text="Bewerken"]')).toBeNull();
  });
});
