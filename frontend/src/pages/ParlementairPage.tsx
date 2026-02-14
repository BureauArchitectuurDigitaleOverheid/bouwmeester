import { useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw, Search } from 'lucide-react';
import { useDebounce } from '@/hooks/useDebounce';
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
} from '@/hooks/useParlementair';
import type { ParlementairItemStatus } from '@/types';
import {
  PARLEMENTAIR_TYPE_LABELS,
  PARLEMENTAIR_TYPE_HEX_COLORS,
  ALL_PARLEMENTAIR_TYPES,
} from '@/types';

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

  const triggerImport = useTriggerParlementairImport();

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <p className="text-sm text-text-secondary">
          Beheer geïmporteerde kamerstukken uit de Tweede en Eerste Kamer.
        </p>
        <Button
          icon={<RefreshCw className={`h-4 w-4 ${triggerImport.isPending ? 'animate-spin' : ''}`} />}
          onClick={() => triggerImport.mutate()}
          disabled={triggerImport.isPending}
        >
          <span className="hidden sm:inline">
            {triggerImport.isPending ? 'Importeren...' : 'Importeer nieuwe kamerstukken'}
          </span>
          <span className="sm:hidden">
            {triggerImport.isPending ? 'Laden...' : 'Importeren'}
          </span>
        </Button>
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
