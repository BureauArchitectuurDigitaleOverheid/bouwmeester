import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { askedQuestions, fakeBackend } from '@/test/authzBackend';
import { SharingManager } from './SharingManager';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const EENHEDEN = [
  { id: 'e1', naam: 'Directie Wonen', type: 'directie' },
  { id: 'e2', naam: 'Directie Bouwen', type: 'directie' },
  { id: 'e3', naam: 'Team Eigen', type: 'team' },
];

// Manages e1; may share it with e2, not with e3 (the caller sits there).
function backend() {
  fakeBackend(mockFetch, {
    eenheden: (action) => (action === 'org:manage' ? { all: false, ids: ['e1'] } : { all: false, ids: [] }),
    decide: ({ action, resource }) =>
      action === 'eenheid:share' && resource.id === 'e1' && resource.properties?.target_eenheid_id === 'e2',
    get: (url) => (url.includes('/api/organisatie') ? EENHEDEN : []),
  });
}

const dropdown = (container: HTMLElement, label: string) =>
  container.querySelector(`nldd-form-field[label="${label}"] nldd-dropdown`);
const submit = (container: HTMLElement) => container.querySelector('nldd-button[text="Toevoegen"]');

/** Pick a value the way nldd-dropdown reports one: a `change` CustomEvent from the host. */
function choose(container: HTMLElement, label: string, value: string) {
  act(() => {
    dropdown(container, label)!.dispatchEvent(new CustomEvent('change', { detail: { value } }));
  });
}

async function openForm(container: HTMLElement) {
  act(() => {
    (container.querySelector('nldd-button[text="Nieuwe deling"]') as HTMLElement).click();
  });
  await waitFor(() =>
    expect(dropdown(container, 'Broneenheid')?.querySelectorAll('option[value="e1"]')).toHaveLength(1),
  );
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe('SharingManager', () => {
  it('asks eenheid:share for the chosen source and target', async () => {
    backend();
    const { container } = renderWithProviders(<SharingManager />);
    await waitFor(() => expect(container.querySelector('nldd-button[text="Nieuwe deling"]')).not.toBeNull());
    await openForm(container);

    choose(container, 'Broneenheid', 'e1');
    choose(container, 'Doeleenheid', 'e3');

    await waitFor(() =>
      expect(askedQuestions(mockFetch)).toContainEqual({
        action: 'eenheid:share',
        resource: { type: 'organisatie_eenheid', id: 'e1', properties: { target_eenheid_id: 'e3' } },
      }),
    );
  });

  it('offers creating the share only for a pair the backend allows', async () => {
    backend();
    const { container } = renderWithProviders(<SharingManager />);
    await waitFor(() => expect(container.querySelector('nldd-button[text="Nieuwe deling"]')).not.toBeNull());
    await openForm(container);

    expect(submit(container)?.hasAttribute('disabled')).toBe(true);

    choose(container, 'Broneenheid', 'e1');
    choose(container, 'Doeleenheid', 'e3');
    await waitFor(() => expect(dropdown(container, 'Doeleenheid')?.hasAttribute('invalid')).toBe(true));
    expect(submit(container)?.hasAttribute('disabled')).toBe(true);

    choose(container, 'Doeleenheid', 'e2');
    await waitFor(() => expect(submit(container)?.hasAttribute('disabled')).toBe(false));
    expect(dropdown(container, 'Doeleenheid')?.hasAttribute('invalid')).toBe(false);
  });
});
