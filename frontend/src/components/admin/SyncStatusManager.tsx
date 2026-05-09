import { Fragment, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, Play, ChevronRight, ChevronDown } from 'lucide-react';
import {
  getSyncStatus,
  getSyncLog,
  triggerSync,
  triggerAllSyncs,
  SYNC_LABELS,
  type SyncEndpoint,
} from '@/api/syncStatus';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';

const ENDPOINTS: SyncEndpoint[] = [
  'tooi',
  'ministeries-csv',
  'rio',
  'organogram',
  'tk-personen',
  'kabinet',
  'abd',
  'historische-kabinetten',
  'onderwijsinstellingen',
  'wikidata-qid',
];

// Mapping van sync-endpoint naar bron-key in tooi_sync_log
const ENDPOINT_NAAR_BRON: Record<SyncEndpoint, string> = {
  'tooi': 'tooi',
  'ministeries-csv': 'ministeries_csv',
  'rio': 'rio',
  'organogram': 'organogram',
  'tk-personen': 'tk_odata',
  'kabinet': 'kabinet',
  'abd': 'abd_scrape',
  'historische-kabinetten': 'kabinet',
  'onderwijsinstellingen': 'onderwijs',
  'wikidata-qid': 'wikidata',
};

function relatieveTijd(iso: string): string {
  const dt = new Date(iso);
  const ms = Date.now() - dt.getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return 'zojuist';
  if (min < 60) return `${min} min geleden`;
  const u = Math.floor(min / 60);
  if (u < 24) return `${u} uur geleden`;
  const d = Math.floor(u / 24);
  return `${d} dagen geleden`;
}

export function SyncStatusManager() {
  const queryClient = useQueryClient();
  const [busyEndpoint, setBusyEndpoint] = useState<SyncEndpoint | 'all' | null>(
    null,
  );
  const [expandedBron, setExpandedBron] = useState<string | null>(null);

  const { data: logEntries = [] } = useQuery({
    queryKey: ['sync-log', expandedBron],
    queryFn: () => getSyncLog(expandedBron ?? undefined, 30),
    enabled: expandedBron !== null,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['sync-status'],
    queryFn: getSyncStatus,
    refetchInterval: 30_000,
  });

  const runMutation = useMutation({
    mutationFn: async (endpoint: SyncEndpoint) => {
      setBusyEndpoint(endpoint);
      try {
        return await triggerSync(endpoint);
      } finally {
        setBusyEndpoint(null);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sync-status'] });
    },
  });

  const runAllMutation = useMutation({
    mutationFn: async () => {
      setBusyEndpoint('all');
      try {
        return await triggerAllSyncs();
      } finally {
        setBusyEndpoint(null);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sync-status'] });
    },
  });

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold mb-1">
            Sync-status overheidsorganisaties
          </h2>
          <p className="text-sm text-text-secondary">
            Per externe bron: laatste sync-tijdstip + handmatige trigger.
            Worker draait dagelijks (TK + kabinet + ABD) en wekelijks
            (TOOI + RIO + CSV + organogram).
          </p>
        </div>
        <Button
          variant="primary"
          icon={<RefreshCw className={busyEndpoint === 'all' ? 'animate-spin h-4 w-4' : 'h-4 w-4'} />}
          onClick={() => runAllMutation.mutate()}
          disabled={busyEndpoint !== null}
        >
          Alles syncen
        </Button>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(data.actief_per_bron).map(([bron, count]) => (
            <Card key={bron}>
              <div className="p-3">
                <div className="text-xs text-text-secondary">
                  Actief — {bron}
                </div>
                <div className="text-2xl font-semibold">{count}</div>
              </div>
            </Card>
          ))}
          <Card>
            <div className="p-3">
              <div className="text-xs text-text-secondary">Open conflicten</div>
              <div className="text-2xl font-semibold">
                {data.open_reconciliations}
              </div>
            </div>
          </Card>
        </div>
      )}

      <Card>
        <table className="w-full">
          <thead className="border-b border-border">
            <tr className="text-xs text-text-secondary text-left">
              <th className="px-4 py-2">Bron</th>
              <th className="px-4 py-2">Laatste run</th>
              <th className="px-4 py-2 w-24"></th>
            </tr>
          </thead>
          <tbody>
            {ENDPOINTS.map((ep) => {
              const bron = ENDPOINT_NAAR_BRON[ep];
              const laatste = data?.laatste_run_per_bron[bron];
              const isExpanded = expandedBron === bron;
              return (
                <Fragment key={ep}>
                  <tr className="border-b border-border last:border-0">
                    <td className="px-4 py-2 text-sm">
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedBron(isExpanded ? null : bron)
                        }
                        className="flex items-center gap-1 hover:text-primary-600"
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-3 w-3" />
                        ) : (
                          <ChevronRight className="h-3 w-3" />
                        )}
                        {SYNC_LABELS[ep]}
                      </button>
                    </td>
                    <td className="px-4 py-2 text-sm text-text-secondary">
                      {laatste
                        ? `${relatieveTijd(laatste)} (${new Date(laatste).toLocaleString('nl-NL')})`
                        : '—'}
                    </td>
                    <td className="px-4 py-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={
                          busyEndpoint === ep ? (
                            <RefreshCw className="animate-spin h-3.5 w-3.5" />
                          ) : (
                            <Play className="h-3.5 w-3.5" />
                          )
                        }
                        onClick={() => runMutation.mutate(ep)}
                        disabled={busyEndpoint !== null}
                      >
                        Run
                      </Button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="border-b border-border">
                      <td colSpan={3} className="px-4 py-2 bg-gray-50">
                        <div className="text-xs text-text-secondary mb-2">
                          Recente log-entries (laatste 30):
                        </div>
                        {logEntries.length === 0 ? (
                          <div className="text-xs text-text-secondary italic">
                            Geen entries.
                          </div>
                        ) : (
                          <div className="space-y-1 max-h-60 overflow-y-auto">
                            {logEntries.map((entry) => (
                              <div
                                key={entry.id}
                                className="text-xs flex items-start gap-2"
                              >
                                <span className="text-text-secondary shrink-0 w-32">
                                  {new Date(entry.created_at).toLocaleString(
                                    'nl-NL',
                                  )}
                                </span>
                                <span
                                  className={`shrink-0 px-1 rounded text-[10px] ${
                                    entry.action === 'add'
                                      ? 'bg-green-100 text-green-700'
                                      : entry.action === 'soft_delete'
                                        ? 'bg-amber-100 text-amber-700'
                                        : entry.action === 'conflict'
                                          ? 'bg-red-100 text-red-700'
                                          : 'bg-gray-100 text-text-secondary'
                                  }`}
                                >
                                  {entry.action}
                                </span>
                                <span className="truncate">
                                  {entry.note ||
                                    (entry.after && typeof entry.after.naam === 'string'
                                      ? entry.after.naam
                                      : entry.tooi_uri || '—')}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
