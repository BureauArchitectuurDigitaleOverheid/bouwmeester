import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw, Search } from 'lucide-react';
import { useDebounce } from '@/hooks/useDebounce';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { ParlementairReviewCard } from '@/components/parlementair/ParlementairReviewCard';
import {
  useParlementairItems,
  useTriggerParlementairImport,
} from '@/hooks/useParlementair';
import type { ParlementairItemStatus, ParlementairItemType } from '@/types';
import { PARLEMENTAIR_TYPE_LABELS } from '@/types';

const statusFilters: { value: ParlementairItemStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Alles' },
  { value: 'imported', label: 'Te beoordelen' },
  { value: 'reviewed', label: 'Beoordeeld' },
  { value: 'rejected', label: 'Afgewezen' },
  { value: 'out_of_scope', label: 'Buiten scope' },
  { value: 'pending', label: 'In wachtrij' },
];

const typeFilters: { value: ParlementairItemType | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle typen' },
  ...(['motie', 'kamervraag', 'toezegging'] as ParlementairItemType[]).map((t) => ({
    value: t,
    label: PARLEMENTAIR_TYPE_LABELS[t] ?? t,
  })),
];

export function ParlementairPage() {
  const [searchParams] = useSearchParams();
  const highlightItemId = searchParams.get('item') || searchParams.get('motie');
  const [statusFilter, setStatusFilter] = useState<ParlementairItemStatus | 'all'>(
    highlightItemId ? 'all' : 'imported'
  );
  const [typeFilter, setTypeFilter] = useState<ParlementairItemType | 'all'>('all');
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebounce(searchInput, 300);
  const filters = {
    ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
    ...(typeFilter !== 'all' ? { type: typeFilter } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
  };
  const { data: imports, isLoading } = useParlementairItems(
    Object.keys(filters).length > 0 ? filters : undefined
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

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Zoeken in kamerstukken..."
          className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 border-b border-border">
        <div className="overflow-x-auto scrollbar-hide">
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
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as ParlementairItemType | 'all')}
          className="sm:ml-auto text-sm border border-border rounded-lg px-3 py-1.5 bg-white text-text-secondary -mb-px"
        >
          {typeFilters.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
      </div>

      {/* Content */}
      {isLoading ? (
        <LoadingSpinner className="py-16" />
      ) : !imports || imports.length === 0 ? (
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
          {imports.map((item) => (
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
