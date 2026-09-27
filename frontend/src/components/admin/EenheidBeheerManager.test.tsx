import { describe, it, expect, vi, beforeEach } from 'vitest';
import { waitFor } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils';
import { askedQuestions, fakeBackend } from '@/test/authzBackend';
import { EenheidBeheerManager } from './EenheidBeheerManager';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const eenheid = (id: string, naam: string) => ({ id, naam, type: 'afdeling', parent_id: null });

beforeEach(() => {
  mockFetch.mockReset();
  fakeBackend(mockFetch, {
    eenheden: (action) => ({ all: false, ids: action === 'org:manage' ? ['e2'] : [] }),
    get: (url) => (url.includes('/api/organisatie') ? [eenheid('e1', 'Team Recht'), eenheid('e2', 'Team Data')] : []),
  });
});

describe('EenheidBeheerManager', () => {
  it('lists only the eenheden the backend names for org:manage, in one request', async () => {
    const { container } = renderWithProviders(<EenheidBeheerManager />);

    await waitFor(() => expect(container.querySelector('nldd-button[text="Team Data"]')).not.toBeNull());
    expect(container.querySelector('nldd-button[text="Team Recht"]')).toBeNull();
    expect(askedQuestions(mockFetch)).toEqual([]);
    const eenhedenCalls = mockFetch.mock.calls.filter(([url]) => String(url).includes('/api/authz/eenheden'));
    expect(eenhedenCalls).toHaveLength(1);
  });
});
