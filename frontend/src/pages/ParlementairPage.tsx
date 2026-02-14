import { useState, useCallback, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw, RotateCcw, Search, ChevronDown } from 'lucide-react';
import { useDebounce } from '@/hooks/useDebounce';
import { useToast } from '@/contexts/ToastContext';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { MultiSelect } from '@/components/common/MultiSelect';
import type { MultiSelectOption } from '@/components/common/MultiSelect';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { ParlementairReviewCard } from '@/components/parlementair/ParlementairReviewCard';
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
import type { ReprocessResult } from '@/api/parlementair';

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

const statusFilters: { value: ParlementairItemStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Alles' },
  { value: 'imported', label: 'Te beoordelen' },
  { value: 'reviewed', label: 'Beoordeeld' },
  { value: 'rejected', label: 'Afgewezen' },
  { value: 'out_of_scope', label: 'Buiten scope' },
  { value: 'pending', label: 'In wachtrij' },
];

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
  const [reprocessDropdownOpen, setReprocessDropdownOpen] = useState(false);
  const reprocessDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (reprocessDropdownRef.current && !reprocessDropdownRef.current.contains(e.target as Node)) {
        setReprocessDropdownOpen(false);
      }
    }
    if (reprocessDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [reprocessDropdownOpen]);

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
    setReprocessDropdownOpen(false);
    const plural = REPROCESS_TYPE_PLURALS[itemType] ?? itemType;
    if (!window.confirm(`Alle ongekoppelde ${plural.toLowerCase()} herverwerken via LLM-matching? Dit kan even duren.`)) return;
    reprocess.mutate(itemType, {
      onSuccess: (result) => {
        if (result.error === 'no_llm') {
          showError('Geen LLM-provider geconfigureerd. Herverwerken is niet mogelijk.');
          return;
        }
        showSuccess(formatReprocessResult(result, plural));
      },
    });
  };

  const handleReprocessAll = async () => {
    setReprocessDropdownOpen(false);
    if (!window.confirm('Alle ongekoppelde kamerstukken herverwerken via LLM-matching? Dit kan even duren.')) return;

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
        // Error already shown by useMutationWithError
        return;
      }
    }
    if (results.length > 0) showSuccess(results.join('\n'));
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
          <div className="relative" ref={reprocessDropdownRef}>
            <Button
              variant="secondary"
              icon={<RotateCcw className={`h-4 w-4 ${reprocess.isPending ? 'animate-spin' : ''}`} />}
              onClick={() => setReprocessDropdownOpen((prev) => !prev)}
              disabled={eitherPending}
              title="Herverwerk kamerstukken die nog geen koppelingen hebben via LLM-matching"
            >
              <span className="hidden sm:inline">
                {reprocess.isPending ? 'Herverwerken...' : 'Herverwerk kamerstukken'}
              </span>
              <span className="sm:hidden">
                {reprocess.isPending ? 'Laden...' : 'Herverwerk'}
              </span>
              <ChevronDown className="h-3.5 w-3.5 ml-1" />
            </Button>
            {reprocessDropdownOpen && (
              <div className="absolute right-0 mt-1 w-56 rounded-md border border-border bg-surface shadow-lg z-50">
                <div className="py-1">
                  <button
                    className="w-full px-4 py-2 text-left text-sm hover:bg-surface-hover"
                    onClick={handleReprocessAll}
                  >
                    Alle kamerstukken
                  </button>
                  {REPROCESS_TYPES.map((t) => (
                    <button
                      key={t}
                      className="w-full px-4 py-2 text-left text-sm hover:bg-surface-hover"
                      onClick={() => handleReprocessType(t)}
                    >
                      {REPROCESS_TYPE_PLURALS[t]}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <Button
            icon={<RefreshCw className={`h-4 w-4 ${triggerImport.isPending ? 'animate-spin' : ''}`} />}
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
        <div className="relative w-full sm:w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Zoek in kamerstukken..."
            className="pl-9"
          />
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
      <div className="flex items-center gap-2 sm:gap-4 border-b border-border overflow-x-auto scrollbar-hide">
        <div className="flex items-center gap-1">
          {statusFilters.map((filter) => (
            <button
              key={filter.value}
              onClick={() => setStatusFilter(filter.value)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap flex-shrink-0 ${
                statusFilter === filter.value
                  ? 'border-primary-900 text-primary-900'
                  : 'border-transparent text-text-secondary hover:text-text hover:border-border'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

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
    </div>
  );
}
