import { useRef } from 'react';
import { useNodeFinancieel, useNodeOpdrachten } from '@/hooks/useOpdrachten';
import {
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OpdrachtStatus,
} from '@/types';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { useNlddEvent } from '@/components/nldd/events';
import { formatCurrencyCompact, calculateUtilization } from '@/utils/format';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import { useOpdrachtCreate } from '@/contexts/OpdrachtCreateContext';

/** An `nldd-list-item[button]` row with its click bridged to React. */
function ClickableListItem({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return (
    <nldd-list-item ref={ref} button>
      {children}
    </nldd-list-item>
  );
}

interface FinancieelOverzichtPanelProps {
  nodeId: string;
  nodeType: string;
}

export function FinancieelOverzichtPanel({ nodeId, nodeType }: FinancieelOverzichtPanelProps) {
  const { data: overzicht, isLoading: loadingOverzicht } = useNodeFinancieel(nodeId);
  const { data: opdrachten = [], isLoading: loadingOpdrachten } = useNodeOpdrachten(nodeId);
  const { openOpdrachtDetail } = useOpdrachtDetail();
  const { openOpdrachtCreate } = useOpdrachtCreate();

  if (loadingOverzicht || loadingOpdrachten) {
    return <nldd-activity-indicator size="24" text="Laden..." show-text />;
  }

  if (!overzicht || overzicht.per_jaar.length === 0) {
    return (
      <nldd-inline-dialog icon="euro-sign" text="Geen financiële gegevens beschikbaar." />
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-gray-50 rounded-lg p-3">
          <nldd-text size="xs" color="secondary">Totaal budget</nldd-text>
          <p className="text-lg font-semibold text-text tabular-nums">{formatCurrencyCompact(overzicht.totaal_budget)}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <nldd-text size="xs" color="secondary">Totaal gerealiseerd</nldd-text>
          <p className="text-lg font-semibold text-text tabular-nums">{formatCurrencyCompact(overzicht.totaal_gerealiseerd)}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <nldd-text size="xs" color="secondary">Uitnutting</nldd-text>
          <p className="text-lg font-semibold text-text">
            {overzicht.uitnutting_percentage != null ? `${overzicht.uitnutting_percentage.toFixed(1)}%` : '-'}
          </p>
          {overzicht.uitnutting_percentage != null && (
            <nldd-progress-bar
              value={Math.min(overzicht.uitnutting_percentage, 100)}
              max={100}
              size="sm"
              value-display="none"
              className="mt-1 block"
            />
          )}
        </div>
      </div>

      {/* Per year breakdown */}
      <div>
        <h4 className="text-sm font-semibold text-text mb-2">Per begrotingsjaar</h4>
        <nldd-table
          columns="minmax(80px,1fr) minmax(100px,1fr) minmax(100px,1fr) minmax(100px,1fr) minmax(100px,1fr)"
          accessible-label="Financieel overzicht per begrotingsjaar"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Jaar" />
            <nldd-text-cell text="Budget" horizontal-alignment="right" />
            <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
            <nldd-text-cell text="Uitnutting" horizontal-alignment="right" />
            <nldd-text-cell text="Opdrachten" horizontal-alignment="right" />
          </nldd-table-row>
          {overzicht.per_jaar.map((j) => {
            const uitn = calculateUtilization(j.budget, j.gerealiseerd);
            return (
              <nldd-table-row key={j.begrotingsjaar}>
                <nldd-text-cell text={String(j.begrotingsjaar)} />
                <nldd-text-cell text={formatCurrencyCompact(j.budget)} horizontal-alignment="right" />
                <nldd-text-cell text={formatCurrencyCompact(j.gerealiseerd)} horizontal-alignment="right" />
                <nldd-text-cell text={uitn != null ? `${uitn.toFixed(1)}%` : '-'} horizontal-alignment="right" />
                <nldd-text-cell text={String(j.opdracht_count)} color="secondary" horizontal-alignment="right" />
              </nldd-table-row>
            );
          })}
        </nldd-table>
      </div>

      {/* Opdrachten list */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold text-text">Opdrachten</h4>
          {nodeType === 'instrument' && (
            <Button
              variant="secondary"
              size="sm"
              icon="plus"
              onClick={() => openOpdrachtCreate({ instrument_id: nodeId })}
            >
              Nieuwe opdracht
            </Button>
          )}
        </div>
        {opdrachten.length > 0 ? (
          <nldd-list variant="box-tinted" dividers="always">
            {opdrachten.map((o) => (
              <ClickableListItem key={o.id} onClick={() => openOpdrachtDetail(o.id)}>
                <nldd-title-cell
                  text={o.titel}
                  overline={`${o.begrotingsjaar} · ${o.opdrachtnemer?.afkorting || o.opdrachtnemer?.naam || '-'}`}
                />
                <nldd-text-cell width="fit-content" text={formatCurrencyCompact(o.budget)} />
                <nldd-text-cell width="fit-content">
                  <Badge variant={OPDRACHT_STATUS_COLORS[o.status as OpdrachtStatus] || 'gray'}>
                    {OPDRACHT_STATUS_LABELS[o.status as OpdrachtStatus] || o.status}
                  </Badge>
                </nldd-text-cell>
              </ClickableListItem>
            ))}
          </nldd-list>
        ) : (
          <nldd-text size="sm" color="secondary">Nog geen opdrachten voor dit instrument.</nldd-text>
        )}
      </div>
    </div>
  );
}
