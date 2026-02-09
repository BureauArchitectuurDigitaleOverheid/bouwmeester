import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { ParlementairReviewCard } from '@/components/parlementair/ParlementairReviewCard';
import {
  useParlementairItems,
  useTriggerParlementairImport,
} from '@/hooks/useParlementair';
import type { ParlementairItemStatus } from '@/types';

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
  const { data: imports, isLoading } = useParlementairItems(
    statusFilter === 'all' ? undefined : { status: statusFilter }
  );
  const triggerImport = useTriggerParlementairImport();

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          Beheer geïmporteerde kamerstukken uit de Tweede en Eerste Kamer.
        </p>
        <Button
          icon={<RefreshCw className={`h-4 w-4 ${triggerImport.isPending ? 'animate-spin' : ''}`} />}
          onClick={() => triggerImport.mutate()}
          disabled={triggerImport.isPending}
        >
          {triggerImport.isPending ? 'Importeren...' : 'Importeer nieuwe kamerstukken'}
        </Button>
      </div>

      {/* Status filter tabs */}
      <div className="flex items-center gap-1 border-b border-border">
        {statusFilters.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setStatusFilter(filter.value)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              statusFilter === filter.value
                ? 'border-primary-900 text-primary-900'
                : 'border-transparent text-text-secondary hover:text-text hover:border-border'
            }`}
          >
            {filter.label}
          </button>
        ))}
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
