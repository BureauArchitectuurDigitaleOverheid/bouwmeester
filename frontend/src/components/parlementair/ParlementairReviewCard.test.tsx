import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { askedQuestions, fakeBackend, type Question } from '@/test/authzBackend';
import type { ParlementairItem, Person } from '@/types';
import { ParlementairReviewCard } from './ParlementairReviewCard';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const person = (id: string, naam: string) => ({ id, naam, is_agent: false }) as Person;
const ME = person('p1', 'Ann');

vi.mock('@/contexts/CurrentPersonContext', () => ({
  useCurrentPerson: () => ({ currentPerson: ME, setDevPersonId: () => {}, people: [] }),
}));

const ITEM: ParlementairItem = {
  id: 'pi1',
  type: 'motie',
  zaak_id: 'z1',
  zaak_nummer: '2026Z00001',
  titel: 'Motie over regels',
  onderwerp: 'Regels',
  bron: 'tweede_kamer',
  status: 'imported',
  corpus_node_id: 'n1',
  created_at: '2026-01-01T00:00:00Z',
  suggested_edges: [
    {
      id: 'se1',
      parlementair_item_id: 'pi1',
      target_node_id: 'n2',
      edge_type_id: 'draagt_bij_aan',
      confidence: 0.9,
      status: 'pending',
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
};

function backend(decide: (q: Question) => boolean) {
  fakeBackend(mockFetch, {
    decide,
    get: (url) => {
      if (url.includes('/api/people')) return [ME, person('p2', 'Bea')];
      if (url.includes('/api/nodes/n1/tags')) return [{ tag: { id: 't1', name: 'Wonen' } }];
      return [];
    },
  });
}

const renderCard = () => renderWithProviders(<ParlementairReviewCard item={ITEM} defaultExpanded />);
const button = (container: HTMLElement, text: string) => container.querySelector(`nldd-button[text="${text}"]`);
const eigenaarOptions = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('nldd-form-field[label="Eigenaar"] nldd-menu-item')).map((el) =>
    el.getAttribute('text'),
  );

const eigenaarField = (container: HTMLElement) =>
  container.querySelector('nldd-form-field[label="Eigenaar"] nldd-combo-box');
/** Pick an option the way the combo box commits one: a `change` CustomEvent. */
function chooseEigenaar(container: HTMLElement, personId: string) {
  act(() => {
    eigenaarField(container)!.dispatchEvent(new CustomEvent('change', { detail: { value: personId } }));
  });
}

beforeEach(() => {
  mockFetch.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

describe('ParlementairReviewCard', () => {
  it('asks parlementair:review on the item node', async () => {
    backend(() => false);
    renderCard();

    await waitFor(() =>
      expect(askedQuestions(mockFetch)).toContainEqual({
        action: 'parlementair:review',
        resource: { type: 'corpus_node', id: 'n1' },
      }),
    );
  });

  it('offers no review actions without parlementair:review', async () => {
    backend((q) => q.action === 'node:update');
    const { container } = renderCard();

    await waitFor(() => expect(askedQuestions(mockFetch).length).toBeGreaterThan(0));
    expect(button(container, 'Beoordeling afronden')).toBeNull();
    expect(button(container, 'Niet relevant')).toBeNull();
    expect(container.querySelector('[accessible-label="Goedkeuren"]')).toBeNull();
    expect(container.querySelector('nldd-form-field[label="Eigenaar"]')).toBeNull();
  });

  it('offers every person as eigenaar, including yourself', async () => {
    backend((q) => q.action === 'parlementair:review');
    const { container } = renderCard();

    await waitFor(() => expect(eigenaarOptions(container)).toContain('Bea'));
    expect(eigenaarOptions(container)).toContain('Ann (mij)');
  });

  it('asks parlementair:name_owner for the chosen eigenaar', async () => {
    backend((q) => q.action === 'parlementair:review');
    const { container } = renderCard();

    await waitFor(() => expect(eigenaarOptions(container)).toContain('Bea'));
    chooseEigenaar(container, 'p2');
    await waitFor(() =>
      expect(askedQuestions(mockFetch)).toContainEqual({
        action: 'parlementair:name_owner',
        resource: { type: 'corpus_node', id: 'n1', properties: { target_person_id: 'p2' } },
      }),
    );
  });

  it('enables completing only when the backend allows naming that eigenaar', async () => {
    backend(
      (q) =>
        q.action === 'parlementair:review' ||
        (q.action === 'parlementair:name_owner' && q.resource.properties?.target_person_id === 'p2'),
    );
    const { container } = renderCard();
    const complete = () => button(container, 'Beoordeling afronden');

    await waitFor(() => expect(eigenaarOptions(container)).toContain('Bea'));
    expect(complete()?.hasAttribute('disabled')).toBe(true);

    chooseEigenaar(container, 'p1');
    await waitFor(() => expect(eigenaarField(container)?.hasAttribute('invalid')).toBe(true));
    expect(complete()?.hasAttribute('disabled')).toBe(true);

    chooseEigenaar(container, 'p2');
    await waitFor(() => expect(complete()?.hasAttribute('disabled')).toBe(false));
    expect(eigenaarField(container)?.hasAttribute('invalid')).toBe(false);
  });

  it('shows the tags read-only to a reviewer without node:update', async () => {
    backend((q) => q.action === 'parlementair:review');
    const { container } = renderCard();

    await waitFor(() => expect(container.querySelector('nldd-tag[text="Wonen"]')).not.toBeNull());
    expect(container.querySelector('nldd-token-field')).toBeNull();
  });

  it('offers tag editing with node:update', async () => {
    backend((q) => q.action === 'parlementair:review' || q.action === 'node:update');
    const { container } = renderCard();

    await waitFor(() => expect(container.querySelector('nldd-token-field')).not.toBeNull());
    expect(container.querySelector('nldd-tag[text="Wonen"]')).toBeNull();
  });
});
