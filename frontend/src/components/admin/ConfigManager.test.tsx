import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, getByNlddText } from '@/test/utils';
import type { AppConfigEntry } from '@/hooks/useAdmin';
import { ConfigManager } from './ConfigManager';

function entry(key: string, editable: boolean): AppConfigEntry {
  return {
    id: key,
    key,
    value: 'x',
    description: null,
    is_secret: false,
    updated_by: null,
    updated_at: '2026-09-01T00:00:00Z',
    created_at: '2026-09-01T00:00:00Z',
    editable,
  };
}

vi.mock('@/hooks/useAdmin', () => ({
  useAppConfig: () => ({
    data: [entry('LLM_MODEL', true), entry('LLM_PROVIDER', false)],
    isLoading: false,
  }),
  useUpdateAppConfig: () => ({ mutate: vi.fn(), isPending: false }),
}));

/** The card of one config key, found through its key label. */
function rowOf(key: string): HTMLElement {
  const label = Array.from(document.querySelectorAll('nldd-text')).find(
    (el) => el.textContent === key,
  );
  const card = label?.closest('nldd-card');
  if (!card) throw new Error(`No config row for ${key}`);
  return card as HTMLElement;
}

describe('ConfigManager', () => {
  it('biedt bewerken alleen aan waar de server het toestaat', () => {
    renderWithProviders(<ConfigManager />);

    expect(getByNlddText('Bewerken', rowOf('LLM_MODEL'))).toBeInTheDocument();
    expect(() => getByNlddText('Bewerken', rowOf('LLM_PROVIDER'))).toThrow();
    expect(getByNlddText('alleen systeembeheerder', rowOf('LLM_PROVIDER'))).toBeInTheDocument();
    expect(() => getByNlddText('alleen systeembeheerder', rowOf('LLM_MODEL'))).toThrow();
  });
});
