import { useState, useMemo, useEffect } from 'react';
import { Plus, Search, RefreshCw, Sparkles } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useOpdrachten, useOpdrachtenSummary, useMatchOpdrachtContactsBulk } from '@/hooks/useOpdrachten';
import { useExterneOrganisaties } from '@/hooks/useExterneOrganisaties';
import { usePeople } from '@/hooks/usePeople';
import { useNodes } from '@/hooks/useNodes';
import { useTriggerFccSync, useFccSchema } from '@/hooks/useFcc';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import { useOpdrachtCreate } from '@/contexts/OpdrachtCreateContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { MultiSelect } from '@/components/common/MultiSelect';
import type { MultiSelectOption } from '@/components/common/MultiSelect';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import type { SelectOption } from '@/components/common/CreatableSelect';
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
  type OpdrachtFilters,
  OpdrachtType,
  OpdrachtStatus,
} from '@/types';
import { Badge } from '@/components/common/Badge';
import { formatCurrency, formatCurrencyCompact } from '@/utils/format';

const MY_OPDRACHTEN_SENTINEL = '__me__';

const TYPE_OPTIONS: MultiSelectOption[] = Object.entries(OPDRACHT_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

const STATUS_OPTIONS: MultiSelectOption[] = Object.entries(OPDRACHT_STATUS_LABELS).map(
  ([value, label]) => ({ value, label }),
);

export function OpdrachtenPage() {
  const { openOpdrachtDetail } = useOpdrachtDetail();
  const { openOpdrachtCreate } = useOpdrachtCreate();
  const { currentPerson } = useCurrentPerson();
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
  const bulkMatch = useMatchOpdrachtContactsBulk();
  const { data: opdrachten = [], isLoading } = useOpdrachten(apiFilters);
  const { data: summary } = useOpdrachtenSummary(apiFilters);
  const { data: externeOrgs = [] } = useExterneOrganisaties();
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
        </div>
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <Button
            variant="secondary"
            icon={<Sparkles className={`h-4 w-4 ${bulkMatch.isPending ? 'animate-pulse' : ''}`} />}
            onClick={() => bulkMatch.mutate(true)}
            disabled={bulkMatch.isPending}
          >
            <span className="hidden sm:inline">{bulkMatch.isPending ? 'Matchen...' : 'Contacten matchen'}</span>
          </Button>
          {fccEnabled && (
            <Button
              variant="secondary"
              icon={<RefreshCw className={`h-4 w-4 ${fccSync.isPending ? 'animate-spin' : ''}`} />}
              onClick={() => fccSync.mutate()}
              disabled={fccSync.isPending}
            >
              <span className="hidden sm:inline">FCC Sync</span>
            </Button>
          )}
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => openOpdrachtCreate()}>
            <span className="hidden sm:inline">Nieuwe opdracht</span>
          </Button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
        <div className="relative w-full sm:w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Zoek opdrachten..."
            className="pl-9"
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
            value={apiFilters.opdrachtnemer_id ?? ''}
            onChange={(v) =>
              setApiFilters((f) => ({
                ...f,
                opdrachtnemer_id: v || undefined,
              }))
            }
            options={opdrachtnemerOptions}
            placeholder="Alle opdrachtnemers"
            onClear={() =>
              setApiFilters((f) => ({ ...f, opdrachtnemer_id: undefined }))
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
              <div
                key={o.id}
                onClick={() => openOpdrachtDetail(o.id)}
                className="bg-surface rounded-xl border border-border p-4 cursor-pointer hover:bg-gray-50 transition-colors space-y-2"
              >
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
      <div className="hidden sm:block bg-surface rounded-xl border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-gray-50/50">
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Titel</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Type</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Jaar</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Opdrachtnemer</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Instrument</th>
              <th className="px-4 py-3 text-right font-medium text-text-secondary">Budget</th>
              <th className="px-4 py-3 text-right font-medium text-text-secondary">Gerealiseerd</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-text-secondary">Laden...</td></tr>
            ) : filteredOpdrachten.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-text-secondary">Geen opdrachten gevonden</td></tr>
            ) : (
              filteredOpdrachten.map((o) => (
                <tr
                  key={o.id}
                  onClick={() => openOpdrachtDetail(o.id)}
                  className="border-b border-border last:border-0 hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-text max-w-[300px] truncate">{o.titel}</td>
                  <td className="px-4 py-3">
                    <Badge variant={OPDRACHT_TYPE_COLORS[o.type as OpdrachtType] || 'gray'}>
                      {OPDRACHT_TYPE_LABELS[o.type as OpdrachtType] || o.type}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-text-secondary">{o.begrotingsjaar}</td>
                  <td className="px-4 py-3 text-text-secondary">{o.opdrachtnemer?.afkorting || o.opdrachtnemer?.naam || '-'}</td>
                  <td className="px-4 py-3 text-text-secondary truncate max-w-[200px]">{o.instrument?.title || '-'}</td>
                  <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(o.budget)}</td>
                  <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(o.gerealiseerd)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <Badge variant={OPDRACHT_STATUS_COLORS[o.status as OpdrachtStatus] || 'gray'}>
                        {OPDRACHT_STATUS_LABELS[o.status as OpdrachtStatus] || o.status}
                      </Badge>
                      {o.fcc_raw_data && (
                        <div className="flex gap-0.5" title="FCC stoplichten">
                          {FCC_TRAFFIC_LIGHT_FIELDS.map(({ key, label }) => {
                            const val = (o.fcc_raw_data as Record<string, unknown>)?.[key] as string | undefined;
                            return val ? (
                              <span
                                key={key}
                                className={`h-2 w-2 rounded-full ${FCC_TRAFFIC_LIGHT_COLORS[val as FccTrafficLight] || 'bg-gray-300'}`}
                                title={`${label}: ${val}`}
                              />
                            ) : null;
                          })}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
          {filteredOpdrachten.length > 0 && (
            <tfoot>
              <tr className="border-t-2 border-border bg-gray-50/50 font-medium">
                <td colSpan={5} className="px-4 py-3 text-text">Totaal ({filteredOpdrachten.length} opdrachten)</td>
                <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(filteredBudget)}</td>
                <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(filteredGerealiseerd)}</td>
                <td className="px-4 py-3"></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
