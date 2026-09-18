import { useCallback, useRef, useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useOpdrachten, useOpdrachtenSummary, useMatchOpdrachtContactsBulk } from '@/hooks/useOpdrachten';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { usePeople } from '@/hooks/usePeople';
import { useNodes } from '@/hooks/useNodes';
import { useTriggerFccSync, useFccSchema, useLastFccSync } from '@/hooks/useFcc';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import { useOpdrachtCreate } from '@/contexts/OpdrachtCreateContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { usePermissions } from '@/hooks/usePermissions';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { MultiSelect } from '@/components/common/MultiSelect';
import type { MultiSelectOption } from '@/components/common/MultiSelect';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { useNlddEvent } from '@/components/nldd/events';
import { useDebounce } from '@/hooks/useDebounce';
import {
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OPDRACHT_TYPE_COLORS,
  FCC_TRAFFIC_LIGHT_COLORS,
  FCC_TRAFFIC_LIGHT_FIELDS,
  NodeType,
  type FccTrafficLight,
  type Opdracht,
  type OpdrachtFilters,
  OpdrachtType,
  OpdrachtStatus,
} from '@/types';
import { Badge } from '@/components/common/Badge';
import { formatCurrency, formatCurrencyCompact } from '@/utils/format';
import { timeAgo } from '@/utils/dates';

const MY_OPDRACHTEN_SENTINEL = '__me__';

const TYPE_OPTIONS: MultiSelectOption[] = Object.entries(OPDRACHT_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

const STATUS_OPTIONS: MultiSelectOption[] = Object.entries(OPDRACHT_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
);

/** FCC "traffic light" dots: an arbitrary per-value color from FCC's own raw
 * data, not one of the five semantic roles, so kept as plain styled spans
 * (same call as LeadListRow's per-initiatief/column chips). */
function FccTrafficLights({ opdracht }: { opdracht: Opdracht }) {
  if (!opdracht.fcc_raw_data) return null;
  return (
    <div className="flex gap-0.5" title="FCC stoplichten">
      {FCC_TRAFFIC_LIGHT_FIELDS.map(({ key, label }) => {
        const val = (opdracht.fcc_raw_data as Record<string, unknown>)?.[key] as string | undefined;
        return val ? (
          <span
            key={key}
            className={`h-2 w-2 rounded-full ${FCC_TRAFFIC_LIGHT_COLORS[val as FccTrafficLight] || 'bg-gray-300'}`}
            title={`${label}: ${val}`}
          />
        ) : null;
      })}
    </div>
  );
}

/** One opdracht row in the desktop table. The title cell carries the click. */
function OpdrachtRow({ opdracht: o, onOpen }: { opdracht: Opdracht; onOpen: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', useCallback(() => onOpen(), [onOpen]));

  return (
    <nldd-table-row>
      <nldd-title-cell ref={ref} text={o.titel} style={{ cursor: 'pointer' }} />
      <nldd-text-cell>
        <Badge variant={OPDRACHT_TYPE_COLORS[o.type as OpdrachtType] || 'gray'}>
          {OPDRACHT_TYPE_LABELS[o.type as OpdrachtType] || o.type}
        </Badge>
      </nldd-text-cell>
      <nldd-text-cell text={String(o.begrotingsjaar)} />
      <nldd-text-cell text={o.opdrachtnemer?.afkorting || o.opdrachtnemer?.naam || '-'} />
      <nldd-text-cell text={o.instrument?.title || '-'} />
      <nldd-text-cell text={formatCurrency(o.budget)} horizontal-alignment="right" />
      <nldd-text-cell text={formatCurrency(o.gerealiseerd)} horizontal-alignment="right" />
      <nldd-text-cell>
        <div className="flex items-center gap-1.5">
          <Badge variant={OPDRACHT_STATUS_COLORS[o.status as OpdrachtStatus] || 'gray'}>
            {OPDRACHT_STATUS_LABELS[o.status as OpdrachtStatus] || o.status}
          </Badge>
          <FccTrafficLights opdracht={o} />
        </div>
      </nldd-text-cell>
    </nldd-table-row>
  );
}

/** One opdracht card in the mobile list. */
function OpdrachtCard({ opdracht: o, onOpen }: { opdracht: Opdracht; onOpen: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', useCallback(() => onOpen(), [onOpen]));

  return (
    <nldd-card ref={ref} button accessible-label={o.titel}>
      <div className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <span className="font-medium text-text text-sm leading-tight">{o.titel}</span>
          <Badge variant={OPDRACHT_STATUS_COLORS[o.status as OpdrachtStatus] || 'gray'}>
            {OPDRACHT_STATUS_LABELS[o.status as OpdrachtStatus] || o.status}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant={OPDRACHT_TYPE_COLORS[o.type as OpdrachtType] || 'gray'}>
            {OPDRACHT_TYPE_LABELS[o.type as OpdrachtType] || o.type}
          </Badge>
          <span className="text-xs text-text-secondary">{o.begrotingsjaar}</span>
          {(o.opdrachtnemer?.afkorting || o.opdrachtnemer?.naam) && (
            <span className="text-xs text-text-secondary">· {o.opdrachtnemer.afkorting || o.opdrachtnemer.naam}</span>
          )}
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-text-secondary">Budget: <span className="text-text tabular-nums">{formatCurrency(o.budget)}</span></span>
          <span className="text-text-secondary">Gerealiseerd: <span className="text-text tabular-nums">{formatCurrency(o.gerealiseerd)}</span></span>
        </div>
      </div>
    </nldd-card>
  );
}

export function OpdrachtenPage() {
  const { openOpdrachtDetail } = useOpdrachtDetail();
  const { openOpdrachtCreate } = useOpdrachtCreate();
  const { currentPerson } = useCurrentPerson();
  const { hasPermission } = usePermissions();
  const [searchParams, setSearchParams] = useSearchParams();

  // API-level filters (sent to backend), seeded from URL params
  const [apiFilters, setApiFilters] = useState<OpdrachtFilters>(() => {
    const initial: OpdrachtFilters = {};
    const v = searchParams.get('verantwoordelijke_id');
    if (v) initial.verantwoordelijke_id = v;
    const i = searchParams.get('instrument_id');
    if (i) initial.instrument_id = i;
    return initial;
  });

  // Keep URL params in sync with apiFilters
  useEffect(() => {
    const params = new URLSearchParams();
    if (apiFilters.verantwoordelijke_id) params.set('verantwoordelijke_id', apiFilters.verantwoordelijke_id);
    if (apiFilters.instrument_id) params.set('instrument_id', apiFilters.instrument_id);
    setSearchParams(params, { replace: true });
  }, [apiFilters.verantwoordelijke_id, apiFilters.instrument_id, setSearchParams]);

  // Client-side filters
  const [searchInput, setSearchInput] = useState('');
  const searchQuery = useDebounce(searchInput, 200);
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());

  const fccSync = useTriggerFccSync();
  const { data: fccSchema } = useFccSchema();
  const fccEnabled = Object.keys(fccSchema?.entity_sets ?? {}).length > 0;
  const { data: lastSync } = useLastFccSync();
  const bulkMatch = useMatchOpdrachtContactsBulk();
  const { data: opdrachten = [], isLoading } = useOpdrachten(apiFilters);
  const { data: summary } = useOpdrachtenSummary(apiFilters);
  const { data: alleEenheden = [] } = useOrganisatieFlat();
  // Externe organisaties zijn nu OrganisatieEenheid-rijen die niet behoren tot
  // de interne hiërarchie of synthetische groepen.
  const externeOrgs = useMemo(
    () =>
      alleEenheden.filter(
        (e) =>
          e.bron !== 'synthetisch' &&
          !['ministerie', 'directoraat_generaal', 'directie', 'afdeling', 'cluster', 'bureau', 'team'].includes(e.type),
      ),
    [alleEenheden],
  );
  const { data: people = [] } = usePeople();
  const { data: instrumenten = [] } = useNodes(NodeType.INSTRUMENT);

  // Derive year options from data
  const yearOptions: SelectOption[] = useMemo(() => {
    const years = [...new Set(opdrachten.map((o) => o.begrotingsjaar))].sort((a, b) => b - a);
    const currentYear = new Date().getFullYear();
    const allYears = years.length > 0 ? years : [currentYear - 1, currentYear, currentYear + 1];
    return allYears.map((y) => ({ value: String(y), label: String(y) }));
  }, [opdrachten]);

  // Derive opdrachtnemer options from externe organisaties
  const opdrachtnemerOptions: SelectOption[] = useMemo(
    () =>
      externeOrgs.map((o) => ({
        value: o.id,
        label: o.afkorting || o.naam,
      })),
    [externeOrgs],
  );

  // Verantwoordelijke options from people, with "Mijn opdrachten" at top
  const verantwoordelijkeOptions: SelectOption[] = useMemo(
    () => [
      ...(currentPerson
        ? [{ value: MY_OPDRACHTEN_SENTINEL, label: `Mijn opdrachten (${currentPerson.naam})` }]
        : []),
      ...people.map((p) => ({ value: p.id, label: p.naam })),
    ],
    [people, currentPerson],
  );

  // Instrument options from nodes
  const instrumentOptions: SelectOption[] = useMemo(
    () => instrumenten.map((n) => ({ value: n.id, label: n.title })),
    [instrumenten],
  );

  // Client-side filtering
  const filteredOpdrachten = useMemo(() => {
    let result = opdrachten;

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (o) =>
          o.titel.toLowerCase().includes(q) ||
          o.opdrachtnemer?.naam?.toLowerCase().includes(q) ||
          o.opdrachtnemer?.afkorting?.toLowerCase().includes(q),
      );
    }

    // Type filter (client-side multi-select)
    if (typeFilter.size > 0) {
      result = result.filter((o) => typeFilter.has(o.type));
    }

    // Status filter (client-side multi-select)
    if (statusFilter.size > 0) {
      result = result.filter((o) => statusFilter.has(o.status));
    }

    return result;
  }, [opdrachten, searchQuery, typeFilter, statusFilter]);

  // Totals from server-side summary (for summary cards)
  const totaalBudget = summary?.totaal_budget ?? 0;
  const totaalGerealiseerd = summary?.totaal_gerealiseerd ?? 0;
  const uitnutting = summary?.uitnutting_percentage ?? 0;

  // Totals from filtered list (for table footer)
  const filteredBudget = filteredOpdrachten.reduce((sum, o) => sum + (o.budget ?? 0), 0);
  const filteredGerealiseerd = filteredOpdrachten.reduce(
    (sum, o) => sum + (o.gerealiseerd ?? 0),
    0,
  );

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Aantal opdrachten</p>
          <p className="text-2xl font-semibold text-text">{summary?.count ?? opdrachten.length}</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Totaal budget</p>
          <p className="text-2xl font-semibold text-text">{formatCurrencyCompact(totaalBudget)}</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Totaal gerealiseerd</p>
          <p className="text-2xl font-semibold text-text">{formatCurrencyCompact(totaalGerealiseerd)}</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Uitnutting</p>
          <p className="text-2xl font-semibold text-text">{uitnutting.toFixed(1)}%</p>
        </div>
      </div>

      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-sm text-text-secondary">
            Beheer opdrachten, subsidies en bijbehorende budgetten.
          </p>
          {fccEnabled && lastSync?.last_synced_at && (
            <p className="text-xs text-text-secondary mt-1">
              Laatste FCC-import: {timeAgo(lastSync.last_synced_at)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {hasPermission('opdracht:update') && (
            <Button
              variant="secondary"
              icon="sparkles"
              loading={bulkMatch.isPending}
              onClick={() => bulkMatch.mutate(true)}
              disabled={bulkMatch.isPending}
            >
              <span className="hidden sm:inline">{bulkMatch.isPending ? 'Matchen...' : 'Contacten & eenheden matchen'}</span>
            </Button>
          )}
          {fccEnabled && hasPermission('fcc:sync') && (
            <Button
              variant="secondary"
              icon="refresh"
              loading={fccSync.isPending}
              onClick={() => fccSync.mutate()}
              disabled={fccSync.isPending}
            >
              <span className="hidden sm:inline">FCC Sync</span>
            </Button>
          )}
          <Button icon="plus" onClick={() => openOpdrachtCreate()}>
            <span className="hidden sm:inline">Nieuwe opdracht</span>
          </Button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
        <div className="w-full sm:w-56">
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Zoek opdrachten..."
          />
        </div>
        <div className="w-full sm:w-44">
          <MultiSelect
            value={typeFilter}
            onChange={setTypeFilter}
            options={TYPE_OPTIONS}
            allLabel="Alle typen"
          />
        </div>
        <div className="w-full sm:w-44">
          <MultiSelect
            value={statusFilter}
            onChange={setStatusFilter}
            options={STATUS_OPTIONS}
            allLabel="Alle statussen"
          />
        </div>
        <div className="w-full sm:w-40">
          <CreatableSelect
            value={apiFilters.begrotingsjaar ? String(apiFilters.begrotingsjaar) : ''}
            onChange={(v) =>
              setApiFilters((f) => ({
                ...f,
                begrotingsjaar: v ? Number(v) : undefined,
              }))
            }
            options={yearOptions}
            placeholder="Alle jaren"
            searchable={false}
            onClear={() =>
              setApiFilters((f) => ({ ...f, begrotingsjaar: undefined }))
            }
          />
        </div>
        <div className="w-full sm:w-52">
          <CreatableSelect
            value={apiFilters.opdrachtnemer_eenheid_id ?? ''}
            onChange={(v) =>
              setApiFilters((f) => ({
                ...f,
                opdrachtnemer_eenheid_id: v || undefined,
              }))
            }
            options={opdrachtnemerOptions}
            placeholder="Alle opdrachtnemers"
            onClear={() =>
              setApiFilters((f) => ({ ...f, opdrachtnemer_eenheid_id: undefined }))
            }
          />
        </div>
        <div className="w-full sm:w-48">
          <CreatableSelect
            value={apiFilters.verantwoordelijke_id === currentPerson?.id ? MY_OPDRACHTEN_SENTINEL : (apiFilters.verantwoordelijke_id ?? '')}
            onChange={(v) => {
              const resolved = v === MY_OPDRACHTEN_SENTINEL ? currentPerson?.id : v;
              setApiFilters((f) => ({
                ...f,
                verantwoordelijke_id: resolved || undefined,
              }));
            }}
            options={verantwoordelijkeOptions}
            placeholder="Alle verantwoordelijken"
            onClear={() =>
              setApiFilters((f) => ({ ...f, verantwoordelijke_id: undefined }))
            }
          />
        </div>
        <div className="w-full sm:w-48">
          <CreatableSelect
            value={apiFilters.instrument_id ?? ''}
            onChange={(v) =>
              setApiFilters((f) => ({
                ...f,
                instrument_id: v || undefined,
              }))
            }
            options={instrumentOptions}
            placeholder="Alle instrumenten"
            onClear={() =>
              setApiFilters((f) => ({ ...f, instrument_id: undefined }))
            }
          />
        </div>
      </div>

      {/* Mobile card list */}
      <div className="sm:hidden space-y-3">
        {isLoading ? (
          <p className="px-4 py-8 text-center text-text-secondary">Laden...</p>
        ) : filteredOpdrachten.length === 0 ? (
          <p className="px-4 py-8 text-center text-text-secondary">Geen opdrachten gevonden</p>
        ) : (
          <>
            {filteredOpdrachten.map((o) => (
              <OpdrachtCard key={o.id} opdracht={o} onOpen={() => openOpdrachtDetail(o.id)} />
            ))}
            <div className="bg-surface rounded-xl border border-border p-4 text-sm font-medium">
              <div className="flex items-center justify-between">
                <span className="text-text">Totaal ({filteredOpdrachten.length})</span>
                <div className="flex gap-4">
                  <span className="text-text tabular-nums">{formatCurrency(filteredBudget)}</span>
                  <span className="text-text tabular-nums">{formatCurrency(filteredGerealiseerd)}</span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block space-y-2">
        <nldd-table
          columns="minmax(200px,1.6fr) 140px 80px minmax(140px,1fr) minmax(140px,1fr) 120px 120px minmax(140px,1fr)"
          accessible-label="Opdrachten"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Titel" />
            <nldd-text-cell text="Type" />
            <nldd-text-cell text="Jaar" />
            <nldd-text-cell text="Opdrachtnemer" />
            <nldd-text-cell text="Instrument" />
            <nldd-text-cell text="Budget" horizontal-alignment="right" />
            <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
            <nldd-text-cell text="Status" />
          </nldd-table-row>
          {isLoading ? (
            <div slot="empty">
              <nldd-inline-dialog variant="loading" text="Laden..." />
            </div>
          ) : filteredOpdrachten.length === 0 ? (
            <div slot="empty">
              <nldd-inline-dialog text="Geen opdrachten gevonden" />
            </div>
          ) : (
            filteredOpdrachten.map((o) => (
              <OpdrachtRow key={o.id} opdracht={o} onOpen={() => openOpdrachtDetail(o.id)} />
            ))
          )}
        </nldd-table>
        {filteredOpdrachten.length > 0 && (
          <div className="flex items-center justify-between px-2 py-2 text-sm font-medium text-text">
            <span>Totaal ({filteredOpdrachten.length} opdrachten)</span>
            <div className="flex gap-6">
              <span className="tabular-nums">{formatCurrency(filteredBudget)}</span>
              <span className="tabular-nums">{formatCurrency(filteredGerealiseerd)}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
