import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, ArrowLeftRight, Check, X } from 'lucide-react';
import {
  listReconciliations,
  mergeReconciliation,
  ignoreReconciliation,
  scanOrphanHandmatig,
  manualMerge,
  type OrphanScanResult,
} from '@/api/reconciliation';
import { getOrganisatieFlatMetHistorisch } from '@/api/organisatie';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';

type Status = 'open' | 'merged' | 'ignored';

function ManualMergePanel() {
  const queryClient = useQueryClient();
  // include_historisch: een duplicaat kan soft-deleted zijn (geldig_tot
  // gevuld); zonder dit kun je zo'n rij niet als bron kiezen.
  const { data: eenheden = [] } = useQuery({
    queryKey: ['organisatie', 'flat', 'historisch'],
    queryFn: getOrganisatieFlatMetHistorisch,
  });

  // source verdwijnt, target blijft. Default-voorstel zodra beide gekozen
  // zijn: de gesyncte rij wordt target (officiële naam + tooi_uri blijven),
  // de handmatige rij wordt source. De admin kan met de swap-knop omkeren.
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [confirming, setConfirming] = useState(false);

  const byId = useMemo(
    () => new Map(eenheden.map((e) => [e.id, e])),
    [eenheden],
  );
  const source = sourceId ? byId.get(sourceId) : undefined;
  const target = targetId ? byId.get(targetId) : undefined;

  const options = useMemo(
    () =>
      eenheden
        .map((e) => ({
          value: e.id,
          label: e.naam,
          description: [
            e.type,
            e.afkorting,
            e.bron && e.bron !== 'handmatig' ? e.bron : null,
            e.geldig_tot ? 'historisch' : null,
          ]
            .filter(Boolean)
            .join(' · '),
        }))
        .sort((a, b) => a.label.localeCompare(b.label, 'nl')),
    [eenheden],
  );

  const mergeMutation = useMutation({
    mutationFn: () => manualMerge(sourceId, targetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
      setSourceId('');
      setTargetId('');
      setConfirming(false);
    },
  });

  // Slim default: zodra source een handmatige rij is en target een
  // gesyncte, klopt de richting al. Is het andersom gekozen, bied de
  // swap prominent aan via een hint (geen auto-swap — admin houdt regie).
  const sourceIsSynced = source?.bron && source.bron !== 'handmatig';
  const targetIsManual = !target?.bron || target.bron === 'handmatig';
  const suggestSwap = Boolean(
    source && target && sourceIsSynced && targetIsManual,
  );

  const swap = () => {
    setSourceId(targetId);
    setTargetId(sourceId);
  };

  const sameRow = sourceId !== '' && sourceId === targetId;
  // Een synthetische rij ('ZBO's en agentschappen', 'Marktpartijen en
  // overige', ...) is een container, geen echte eenheid. FK's daarheen
  // verhuizen is vrijwel altijd fout — blokkeer het als doel.
  const targetIsSynthetic = target?.bron === 'synthetisch';
  const canMerge = source && target && !sameRow && !targetIsSynthetic;

  return (
    <Card>
      <div className="p-4 space-y-3">
        <div>
          <h3 className="font-semibold text-sm mb-1">Handmatig mergen</h3>
          <p className="text-sm text-text-secondary">
            Twee eenheden samenvoegen die de scan niet vangt (bv. een
            seed-DG naast een organogram-rij met net andere naam). Alle
            plaatsingen, leads, opdrachten en sub-eenheden van de{' '}
            <strong>bron</strong> verhuizen naar het <strong>doel</strong>;
            de bron wordt verwijderd. Hou als doel de gesyncte rij aan
            (officiële naam en TOOI-koppeling blijven dan staan).
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-3 items-end">
          <CreatableSelect
            label="Bron (verdwijnt)"
            value={sourceId}
            onChange={(v) => {
              setSourceId(v);
              setConfirming(false);
            }}
            options={options}
            placeholder="Zoek eenheid…"
            emptyMessage="Geen eenheid gevonden"
          />
          <button
            type="button"
            onClick={swap}
            disabled={!sourceId && !targetId}
            title="Bron en doel omwisselen"
            className="mb-1 p-2 rounded text-text-secondary hover:bg-gray-100 disabled:opacity-40"
          >
            <ArrowLeftRight className="h-5 w-5" />
          </button>
          <CreatableSelect
            label="Doel (blijft)"
            value={targetId}
            onChange={(v) => {
              setTargetId(v);
              setConfirming(false);
            }}
            options={options}
            placeholder="Zoek eenheid…"
            emptyMessage="Geen eenheid gevonden"
          />
        </div>

        {sameRow && (
          <p className="text-sm text-red-600">
            Bron en doel zijn dezelfde eenheid.
          </p>
        )}

        {targetIsSynthetic && (
          <p className="text-sm text-red-600">
            Het doel is een synthetische groep, geen echte eenheid. Kies
            een echte organisatie-eenheid als doel.
          </p>
        )}

        {suggestSwap && (
          <p className="text-sm text-amber-700">
            De bron is een gesyncte rij ({source?.bron}) en het doel
            handmatig. Meestal wil je het andersom zodat de gesyncte rij
            blijft bestaan.{' '}
            <button
              type="button"
              onClick={swap}
              className="underline font-medium"
            >
              Omwisselen
            </button>
          </p>
        )}

        {canMerge && !confirming && (
          <div className="flex justify-end">
            <Button variant="primary" onClick={() => setConfirming(true)}>
              Mergen…
            </Button>
          </div>
        )}

        {canMerge && confirming && (
          <div className="border border-red-200 bg-red-50 rounded p-3 space-y-3">
            <p className="text-sm">
              <strong>{source?.naam}</strong> wordt verwijderd. Alle
              referenties verhuizen naar <strong>{target?.naam}</strong>
              {target?.bron && target.bron !== 'handmatig'
                ? ` (${target.bron})`
                : ''}
              . Dit is niet terug te draaien.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => setConfirming(false)}
                disabled={mergeMutation.isPending}
              >
                Annuleren
              </Button>
              <Button
                variant="primary"
                onClick={() => mergeMutation.mutate()}
                disabled={mergeMutation.isPending}
              >
                {mergeMutation.isPending
                  ? 'Bezig…'
                  : 'Definitief mergen'}
              </Button>
            </div>
          </div>
        )}

        {mergeMutation.isError && (
          <p className="text-sm text-red-600">
            Merge mislukt:{' '}
            {mergeMutation.error instanceof Error
              ? mergeMutation.error.message
              : 'onbekende fout'}
          </p>
        )}
        {mergeMutation.isSuccess && (
          <p className="text-sm text-green-700">Merge voltooid.</p>
        )}
      </div>
    </Card>
  );
}

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

      <ManualMergePanel />

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
