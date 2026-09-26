import { describe, it, expect, vi, beforeEach } from 'vitest';
import { waitFor } from '@testing-library/react';
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
    get: (url) => (url.includes('/api/people') ? [ME, person('p2', 'Bea')] : []),
  });
}

const renderCard = () => renderWithProviders(<ParlementairReviewCard item={ITEM} defaultExpanded />);
const button = (container: HTMLElement, text: string) => container.querySelector(`nldd-button[text="${text}"]`);
const eigenaarOptions = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('nldd-form-field[label="Eigenaar"] nldd-menu-item')).map((el) =>
    el.getAttribute('text'),
  );

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

  it('offers the review, but not naming yourself eigenaar without node:update', async () => {
    backend((q) => q.action === 'parlementair:review');
    const { container } = renderCard();

    await waitFor(() => expect(button(container, 'Beoordeling afronden')).not.toBeNull());
    expect(container.querySelector('[accessible-label="Goedkeuren"]')).not.toBeNull();
    await waitFor(() => expect(eigenaarOptions(container)).toContain('Bea'));
    expect(eigenaarOptions(container)).not.toContain('Ann (mij)');
  });

  it('offers "(mij)" when the reviewer may edit the node', async () => {
    backend((q) => q.action === 'parlementair:review' || q.action === 'node:update');
    const { container } = renderCard();

    await waitFor(() => expect(eigenaarOptions(container)).toContain('Ann (mij)'));
  });
});
