import { Plus } from 'lucide-react';
import { useNodeFinancieel, useNodeOpdrachten } from '@/hooks/useOpdrachten';
import {
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OpdrachtStatus,
} from '@/types';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { formatCurrency } from '@/utils/format';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import { useOpdrachtCreate } from '@/contexts/OpdrachtCreateContext';

interface FinancieelOverzichtPanelProps {
  nodeId: string;
}

export function FinancieelOverzichtPanel({ nodeId }: FinancieelOverzichtPanelProps) {
  const { data: overzicht, isLoading: loadingOverzicht } = useNodeFinancieel(nodeId);
  const { data: opdrachten = [], isLoading: loadingOpdrachten } = useNodeOpdrachten(nodeId);
  const { openOpdrachtDetail } = useOpdrachtDetail();
  const { openOpdrachtCreate } = useOpdrachtCreate();

  if (loadingOverzicht || loadingOpdrachten) {
    return <div className="text-sm text-text-secondary py-4">Laden...</div>;
  }

  if (!overzicht || overzicht.per_jaar.length === 0) {
    return (
      <div className="text-sm text-text-secondary py-4">
        Geen financiële gegevens beschikbaar.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-text-secondary">Totaal budget</p>
          <p className="text-lg font-semibold text-text tabular-nums">{formatCurrency(overzicht.totaal_budget)}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-text-secondary">Totaal gerealiseerd</p>
          <p className="text-lg font-semibold text-text tabular-nums">{formatCurrency(overzicht.totaal_gerealiseerd)}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-text-secondary">Uitnutting</p>
          <p className="text-lg font-semibold text-text">
            {overzicht.uitnutting_percentage != null ? `${overzicht.uitnutting_percentage.toFixed(1)}%` : '-'}
          </p>
          {overzicht.uitnutting_percentage != null && (
            <div className="h-1.5 rounded-full bg-gray-200 mt-1 overflow-hidden">
              <div
                className="h-full rounded-full bg-primary-500"
                style={{ width: `${Math.min(overzicht.uitnutting_percentage, 100)}%` }}
              />
            </div>
          )}
        </div>
      </div>

      {/* Per year breakdown */}
      <div>
        <h4 className="text-sm font-semibold text-text mb-2">Per begrotingsjaar</h4>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="py-2 text-left text-text-secondary font-medium">Jaar</th>
              <th className="py-2 text-right text-text-secondary font-medium">Budget</th>
              <th className="py-2 text-right text-text-secondary font-medium">Gerealiseerd</th>
              <th className="py-2 text-right text-text-secondary font-medium">Uitnutting</th>
              <th className="py-2 text-right text-text-secondary font-medium">Opdrachten</th>
            </tr>
          </thead>
          <tbody>
            {overzicht.per_jaar.map((j) => {
              const bud = Number(j.budget) || 0;
              const uitn = bud > 0 ? (Number(j.gerealiseerd) || 0) / bud * 100 : null;
              return (
                <tr key={j.begrotingsjaar} className="border-b border-border last:border-0">
                  <td className="py-2 font-medium text-text">{j.begrotingsjaar}</td>
                  <td className="py-2 text-right text-text tabular-nums">{formatCurrency(j.budget)}</td>
                  <td className="py-2 text-right text-text tabular-nums">{formatCurrency(j.gerealiseerd)}</td>
                  <td className="py-2 text-right text-text">{uitn != null ? `${uitn.toFixed(1)}%` : '-'}</td>
                  <td className="py-2 text-right text-text-secondary">{j.opdracht_count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Opdrachten list */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold text-text">Opdrachten</h4>
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus className="h-3.5 w-3.5" />}
            onClick={() => openOpdrachtCreate({ instrument_id: nodeId })}
          >
            Nieuwe opdracht
          </Button>
        </div>
        {opdrachten.length > 0 ? (
          <div className="space-y-2">
            {opdrachten.map((o) => (
              <div
                key={o.id}
                onClick={() => openOpdrachtDetail(o.id)}
                className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100 transition-colors"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-text truncate">{o.titel}</p>
                  <p className="text-xs text-text-secondary">
                    {o.begrotingsjaar} &middot; {o.opdrachtnemer?.afkorting || o.opdrachtnemer?.naam || '-'}
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-sm text-text tabular-nums">{formatCurrency(o.budget)}</span>
                  <Badge variant={OPDRACHT_STATUS_COLORS[o.status as OpdrachtStatus] || 'gray'}>
                    {OPDRACHT_STATUS_LABELS[o.status as OpdrachtStatus] || o.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-secondary">Nog geen opdrachten voor dit instrument.</p>
        )}
      </div>
    </div>
  );
}
