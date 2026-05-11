import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Check, X } from 'lucide-react';
import {
  listReconciliations,
  mergeReconciliation,
  ignoreReconciliation,
  scanOrphanHandmatig,
  type OrphanScanResult,
} from '@/api/reconciliation';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';

type Status = 'open' | 'merged' | 'ignored';

export function ReconciliationManager() {
  const [status, setStatus] = useState<Status>('open');
  const queryClient = useQueryClient();

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['reconciliation', status],
    queryFn: () => listReconciliations(status),
  });

  const mergeMutation = useMutation({
    mutationFn: (id: string) => mergeReconciliation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });

  const ignoreMutation = useMutation({
    mutationFn: (id: string) => ignoreReconciliation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reconciliation'] });
    },
  });

  const [scanResult, setScanResult] = useState<OrphanScanResult | null>(null);
  const orphanScanMutation = useMutation({
    mutationFn: scanOrphanHandmatig,
    onSuccess: (data) => {
      setScanResult(data);
      queryClient.invalidateQueries({ queryKey: ['reconciliation'] });
    },
  });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold mb-1">
          Reconciliatie van handmatige rijen met TOOI-data
        </h2>
        <p className="text-sm text-text-secondary">
          TOOI-sync detecteert organisaties die ook handmatig zijn
          aangemaakt. Mergen voegt de handmatige rij samen met de TOOI-rij
          (alle leads, opdrachten en plaatsingen verhuizen). Negeren laat
          beide rijen bestaan.
        </p>
      </div>

      <Card>
        <div className="p-3 flex items-center justify-between gap-3 text-sm">
          <div>
            <strong>Scan op afkorting/naam-match:</strong> zoekt handmatige
            rijen (vaak FCC-import) die alsnog matchen op een TOOI-rij.
            Genereert open reconciliations.
            {scanResult && (
              <span className="ml-2 text-text-secondary">
                Laatste run: {scanResult.scanned} gescand,
                {' '}{scanResult.found_match} matches,
                {' '}{scanResult.new_reconciliations} nieuw,
                {' '}{scanResult.already_pending} al open.
              </span>
            )}
          </div>
          <Button
            onClick={() => orphanScanMutation.mutate()}
            disabled={orphanScanMutation.isPending}
            variant="secondary"
          >
            {orphanScanMutation.isPending ? 'Bezig…' : 'Scan starten'}
          </Button>
        </div>
      </Card>

      <div className="flex gap-2">
        {(['open', 'merged', 'ignored'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`px-3 py-1.5 text-sm rounded ${
              status === s
                ? 'bg-primary-100 text-primary-700 font-medium'
                : 'text-text-secondary hover:bg-gray-100'
            }`}
          >
            {s === 'open' ? 'Open' : s === 'merged' ? 'Gemerged' : 'Genegeerd'}
            <span className="ml-1.5 text-xs opacity-70">
              {status === s ? `(${items.length})` : ''}
            </span>
          </button>
        ))}
      </div>

      {isLoading && <LoadingSpinner />}

      {!isLoading && items.length === 0 && (
        <Card>
          <div className="p-6 text-center text-text-secondary text-sm">
            Geen{' '}
            {status === 'open'
              ? 'open reconciliaties'
              : status === 'merged'
                ? 'gemergede reconciliaties'
                : 'genegeerde reconciliaties'}
            .
          </div>
        </Card>
      )}

      {items.map((item) => (
        <Card key={item.id}>
          <div className="p-4">
            <div className="flex items-center gap-3 mb-3">
              <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-text-secondary">
                {item.match_reden}
              </span>
              <span className="text-xs text-text-secondary">
                {new Date(item.created_at).toLocaleDateString('nl-NL', {
                  day: '2-digit',
                  month: 'short',
                  year: 'numeric',
                })}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-4 items-center">
              {/* Handmatige rij */}
              <div className="border border-amber-200 bg-amber-50 rounded p-3">
                <div className="text-xs font-medium text-amber-700 mb-1">
                  Handmatig
                </div>
                <div className="font-medium">{item.handmatige_naam}</div>
                {item.handmatige_afkorting && (
                  <div className="text-xs text-text-secondary">
                    {item.handmatige_afkorting}
                  </div>
                )}
              </div>

              <ArrowRight className="h-5 w-5 text-text-secondary mx-auto" />

              {/* Kandidaat */}
              <div className="border border-blue-200 bg-blue-50 rounded p-3">
                <div className="text-xs font-medium text-blue-700 mb-1">
                  {item.kandidaat_bron.toUpperCase()}
                </div>
                <div className="font-medium">{item.kandidaat_naam ?? '—'}</div>
                {item.kandidaat_tooi_uri && (
                  <div className="text-xs text-text-secondary truncate font-mono">
                    {item.kandidaat_tooi_uri}
                  </div>
                )}
              </div>
            </div>

            {status === 'open' && (
              <div className="flex justify-end gap-2 mt-4">
                <Button
                  variant="secondary"
                  onClick={() => ignoreMutation.mutate(item.id)}
                  disabled={
                    ignoreMutation.isPending && ignoreMutation.variables === item.id
                  }
                >
                  <X className="h-4 w-4" />
                  Negeren
                </Button>
                <Button
                  variant="primary"
                  onClick={() => mergeMutation.mutate(item.id)}
                  disabled={
                    !item.kandidaat_id ||
                    (mergeMutation.isPending && mergeMutation.variables === item.id)
                  }
                  title={
                    !item.kandidaat_id
                      ? 'Kandidaat-rij is verwijderd; kan niet mergen'
                      : 'Verplaats alle plaatsingen, leads en opdrachten naar de kandidaat-rij en verwijder de handmatige rij'
                  }
                >
                  <Check className="h-4 w-4" />
                  Mergen
                </Button>
              </div>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
