import { useState, useCallback, useId, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useDebounce } from '@/hooks/useDebounce';
import { useToast } from '@/contexts/ToastContext';
import { Button } from '@/components/common/Button';
import { MultiSelect } from '@/components/common/MultiSelect';
import type { MultiSelectOption } from '@/components/common/MultiSelect';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { ParlementairReviewCard } from '@/components/parlementair/ParlementairReviewCard';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import {
  useParlementairItems,
  useTriggerParlementairImport,
  useReprocessParlementairItems,
} from '@/hooks/useParlementair';
import type { ParlementairItemStatus } from '@/types';
import {
  PARLEMENTAIR_TYPE_LABELS,
  PARLEMENTAIR_TYPE_HEX_COLORS,
  ALL_PARLEMENTAIR_TYPES,
} from '@/types';
import type { ReprocessResult } from '@/types';

const REPROCESS_TYPES = ['toezegging', 'motie', 'kamervraag'] as const;

const REPROCESS_TYPE_PLURALS: Record<string, string> = {
  toezegging: 'Toezeggingen',
  motie: 'Moties',
  kamervraag: 'Kamervragen',
};

const parlementairTypeOptions: MultiSelectOption[] = ALL_PARLEMENTAIR_TYPES.map((t) => ({
  value: t,
  label: PARLEMENTAIR_TYPE_LABELS[t] ?? t,
  color: PARLEMENTAIR_TYPE_HEX_COLORS[t],
}));

/** `nldd-menu-item` with a React-shaped onClick, listening to its `select` event. */
function MenuItem({ text, onClick }: { text: string; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', onClick);
  return <nldd-menu-item ref={ref} text={text} />;
}

/** The kamerstukken search field: `nldd-search-field` with its `input` event bridged to React. */
function ParlementairSearchField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return (
    <nldd-search-field
      ref={ref}
      value={value}
      placeholder="Zoek in kamerstukken..."
      accessible-label="Zoek in kamerstukken"
    />
  );
}

const statusFilters: { value: ParlementairItemStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Alles' },
  { value: 'imported', label: 'Te beoordelen' },
  { value: 'reviewed', label: 'Beoordeeld' },
  { value: 'rejected', label: 'Afgewezen' },
  { value: 'out_of_scope', label: 'Buiten scope' },
  { value: 'pending', label: 'In wachtrij' },
];

/**
 * Content-switching tab bar for the status filter. `nldd-tab-bar` self-manages
 * `current` on click and arrow-key navigation (non-`navigation` mode), so this
 * only needs to read the id back off `tabchange`'s `detail.item` — same
 * pattern as AdminPage's tab bar.
 */
function StatusTabBar({
  value,
  onChange,
}: {
  value: ParlementairItemStatus | 'all';
  onChange: (v: ParlementairItemStatus | 'all') => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(
    ref,
    'tabchange',
    useCallback(
      (event: Event) => {
        const item = (event as CustomEvent<{ item?: HTMLElement }>).detail?.item;
        const next = item?.dataset.statusValue as ParlementairItemStatus | 'all' | undefined;
        if (next) onChange(next);
      },
      [onChange],
    ),
  );

  return (
    <nldd-tab-bar ref={ref} variant="text">
      {statusFilters.map((filter) => (
        <nldd-tab-bar-item
          key={filter.value}
          text={filter.label}
          current={value === filter.value ? true : undefined}
          data-status-value={filter.value}
        />
      ))}
    </nldd-tab-bar>
  );
}

export function ParlementairPage() {
  const [searchParams] = useSearchParams();
  const highlightItemId = searchParams.get('item') || searchParams.get('motie');
  const [statusFilter, setStatusFilter] = useState<ParlementairItemStatus | 'all'>(
    highlightItemId ? 'all' : 'imported'
  );
  const [enabledTypes, setEnabledTypes] = useState<Set<string>>(
    () => new Set(ALL_PARLEMENTAIR_TYPES),
  );
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebounce(searchInput, 300);

  const handleTypesChange = useCallback((next: Set<string>) => {
    setEnabledTypes(next);
  }, []);

  // Build API filters — only send type filter when not all types are selected
  const allTypesSelected = enabledTypes.size === ALL_PARLEMENTAIR_TYPES.length;
  const filters = {
    ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
  };
  const { data: imports, isLoading } = useParlementairItems(
    Object.keys(filters).length > 0 ? filters : undefined
  );

  // Client-side type filter
  const filteredImports = imports?.filter((item) =>
    allTypesSelected || enabledTypes.has(item.type)
  );

  const { showSuccess, showError } = useToast();
  const triggerImport = useTriggerParlementairImport();
  const [reprocessConfirm, setReprocessConfirm] = useState<string | null>(null);
  const reprocessMenuTriggerId = useId();

  const formatReprocessResult = (result: ReprocessResult, plural: string) => {
    if (result.total === 0) return `Geen ongekoppelde ${plural.toLowerCase()} om te herverwerken.`;
    const parts: string[] = [];
    if (result.matched > 0) parts.push(`${result.matched} gekoppeld`);
    if (result.out_of_scope > 0) parts.push(`${result.out_of_scope} buiten scope`);
    if (result.skipped > 0) parts.push(`${result.skipped} overgeslagen`);
    return `${result.total} ${plural.toLowerCase()} herverwerkt: ${parts.join(', ')}.`;
  };

  const reprocess = useReprocessParlementairItems();

  const handleReprocessType = (itemType: string) => {
    setReprocessConfirm(itemType);
  };

  const handleReprocessAll = () => {
    setReprocessConfirm('__all__');
  };

  const executeReprocess = async () => {
    if (!reprocessConfirm) return;
    setReprocessConfirm(null);

    if (reprocessConfirm === '__all__') {
      const results: string[] = [];
      for (const t of REPROCESS_TYPES) {
        try {
          const result = await reprocess.mutateAsync(t);
          if (result.error === 'no_llm') {
            showError('Geen LLM-provider geconfigureerd. Herverwerken is niet mogelijk.');
            return;
          }
          const plural = REPROCESS_TYPE_PLURALS[t] ?? t;
          results.push(formatReprocessResult(result, plural));
        } catch {
          return;
        }
      }
      if (results.length > 0) showSuccess(results.join('\n'));
    } else {
      const plural = REPROCESS_TYPE_PLURALS[reprocessConfirm] ?? reprocessConfirm;
      reprocess.mutate(reprocessConfirm, {
        onSuccess: (result) => {
          if (result.error === 'no_llm') {
            showError('Geen LLM-provider geconfigureerd. Herverwerken is niet mogelijk.');
            return;
          }
          showSuccess(formatReprocessResult(result, plural));
        },
      });
    }
  };

  const eitherPending = triggerImport.isPending || reprocess.isPending;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <p className="text-sm text-text-secondary">
          Beheer geïmporteerde kamerstukken uit de Tweede en Eerste Kamer.
        </p>
        <div className="flex items-center gap-2">
          <div>
            <Button
              id={reprocessMenuTriggerId}
              variant="secondary"
              icon="undo"
              loading={reprocess.isPending}
              disabled={eitherPending}
              title="Herverwerk kamerstukken die nog geen koppelingen hebben via LLM-matching"
            >
              <span className="hidden sm:inline">
                {reprocess.isPending ? 'Herverwerken...' : 'Herverwerk kamerstukken'}
              </span>
              <span className="sm:hidden">
                {reprocess.isPending ? 'Laden...' : 'Herverwerk'}
              </span>
            </Button>
            <nldd-menu anchor={reprocessMenuTriggerId} accessible-label="Herverwerkopties">
              <MenuItem text="Alle kamerstukken" onClick={handleReprocessAll} />
              {REPROCESS_TYPES.map((t) => (
                <MenuItem key={t} text={REPROCESS_TYPE_PLURALS[t]} onClick={() => handleReprocessType(t)} />
              ))}
            </nldd-menu>
          </div>
          <Button
            icon="refresh"
            loading={triggerImport.isPending}
            onClick={() => triggerImport.mutate()}
            disabled={eitherPending}
            title="Haal nieuwe kamerstukken op uit de Tweede en Eerste Kamer"
          >
            <span className="hidden sm:inline">
              {triggerImport.isPending ? 'Importeren...' : 'Importeer nieuwe kamerstukken'}
            </span>
            <span className="sm:hidden">
              {triggerImport.isPending ? 'Laden...' : 'Importeren'}
            </span>
          </Button>
        </div>
      </div>

      {/* Filter bar (matching Corpus page layout) */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
        <div className="w-full sm:w-56">
          <ParlementairSearchField value={searchInput} onChange={setSearchInput} />
        </div>
        <div className="w-full sm:w-52">
          <MultiSelect
            value={enabledTypes}
            onChange={handleTypesChange}
            options={parlementairTypeOptions}
            allLabel="Alle typen"
          />
        </div>
      </div>

      {/* Status tabs */}
      <StatusTabBar value={statusFilter} onChange={setStatusFilter} />

      {/* Content */}
      {isLoading ? (
        <LoadingSpinner className="py-16" />
      ) : !filteredImports || filteredImports.length === 0 ? (
        <EmptyState
          title="Geen kamerstukken gevonden"
          description={
            statusFilter === 'imported'
              ? 'Er zijn geen kamerstukken die beoordeeld moeten worden.'
              : 'Er zijn geen kamerstukken met deze status.'
          }
        />
      ) : (
        <div className="space-y-3">
          {filteredImports.map((item) => (
            <ParlementairReviewCard
              key={item.id}
              item={item}
              defaultExpanded={item.id === highlightItemId}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!reprocessConfirm}
        onClose={() => setReprocessConfirm(null)}
        onConfirm={executeReprocess}
        title="Herverwerken bevestigen"
        confirmLabel="Herverwerken"
        loading={reprocess.isPending}
      >
        <p>
          {reprocessConfirm === '__all__'
            ? 'Alle ongekoppelde kamerstukken herverwerken via LLM-matching? Dit kan even duren.'
            : `Alle ongekoppelde ${(REPROCESS_TYPE_PLURALS[reprocessConfirm ?? ''] ?? reprocessConfirm ?? '').toLowerCase()} herverwerken via LLM-matching? Dit kan even duren.`}
        </p>
      </ConfirmDialog>
    </div>
  );
}
