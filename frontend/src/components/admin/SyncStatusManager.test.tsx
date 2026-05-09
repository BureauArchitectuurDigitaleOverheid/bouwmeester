import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/utils';
import { SyncStatusManager } from './SyncStatusManager';

vi.mock('@/api/syncStatus', async () => {
  const actual = await vi.importActual<typeof import('@/api/syncStatus')>(
    '@/api/syncStatus',
  );
  return {
    ...actual,
    getSyncStatus: vi.fn(async () => ({
      laatste_run_per_bron: {
        tooi: '2026-05-09T08:00:00Z',
        kabinet: '2026-05-08T04:00:00Z',
      },
      actief_per_bron: { tooi: 1437, handmatig: 12 },
      open_reconciliations: 2,
    })),
    getSyncLog: vi.fn(async () => [
      {
        id: 'log-1',
        sync_run_id: 'run-1',
        bron: 'tooi',
        action: 'add',
        tooi_uri: 'https://identifier.overheid.nl/tooi/id/oorg/oorg00001',
        organisatie_eenheid_id: 'org-1',
        person_id: null,
        before: null,
        after: { naam: 'Gemeente Verzonnen' },
        note: null,
        created_at: '2026-05-09T08:00:01Z',
      },
      {
        id: 'log-2',
        sync_run_id: 'run-1',
        bron: 'tooi',
        action: 'soft_delete',
        tooi_uri: null,
        organisatie_eenheid_id: 'org-2',
        person_id: null,
        before: { naam: 'Oude organisatie' },
        after: null,
        note: 'afwezig in feed sinds 2026-05-08',
        created_at: '2026-05-09T08:00:02Z',
      },
    ]),
    triggerSync: vi.fn(),
    triggerAllSyncs: vi.fn(),
  };
});

describe('SyncStatusManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders sync-bron rijen met laatste run-tijd', async () => {
    renderWithProviders(<SyncStatusManager />);

    expect(await screen.findByText('TOOI-waardelijsten')).toBeInTheDocument();
    expect(screen.getByText('Kabinet (rijksoverheid.nl)')).toBeInTheDocument();
  });

  it('toont actief-per-bron tellers en open conflicten', async () => {
    renderWithProviders(<SyncStatusManager />);

    await waitFor(() => {
      expect(screen.getByText('1437')).toBeInTheDocument();
    });
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('Open conflicten')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('vouwt log-entries uit bij klikken op rij', async () => {
    const user = userEvent.setup();
    const { getSyncLog } = await import('@/api/syncStatus');

    renderWithProviders(<SyncStatusManager />);

    const tooiButton = await screen.findByRole('button', {
      name: /TOOI-waardelijsten/,
    });

    await user.click(tooiButton);

    await waitFor(() => {
      expect(getSyncLog).toHaveBeenCalledWith('tooi', 30);
    });

    expect(await screen.findByText('Gemeente Verzonnen')).toBeInTheDocument();
    expect(
      screen.getByText('afwezig in feed sinds 2026-05-08'),
    ).toBeInTheDocument();
  });

  it('rendert action-badges met action-naam', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SyncStatusManager />);

    const tooiButton = await screen.findByRole('button', {
      name: /TOOI-waardelijsten/,
    });
    await user.click(tooiButton);

    expect(await screen.findByText('add')).toBeInTheDocument();
    expect(screen.getByText('soft_delete')).toBeInTheDocument();
  });

  it('vouwt log weer in bij tweede klik', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SyncStatusManager />);

    const tooiButton = await screen.findByRole('button', {
      name: /TOOI-waardelijsten/,
    });
    await user.click(tooiButton);
    expect(await screen.findByText('Gemeente Verzonnen')).toBeInTheDocument();

    await user.click(tooiButton);
    await waitFor(() => {
      expect(screen.queryByText('Gemeente Verzonnen')).not.toBeInTheDocument();
    });
  });
});
