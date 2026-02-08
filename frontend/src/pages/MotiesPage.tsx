import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { MotieReviewCard } from '@/components/moties/MotieReviewCard';
import {
  useMotieImports,
  useTriggerMotieImport,
} from '@/hooks/useMoties';
import type { MotieImportStatus } from '@/types';

const statusFilters: { value: MotieImportStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Alles' },
  { value: 'imported', label: 'Te beoordelen' },
  { value: 'reviewed', label: 'Beoordeeld' },
  { value: 'rejected', label: 'Afgewezen' },
  { value: 'out_of_scope', label: 'Buiten scope' },
  { value: 'pending', label: 'In wachtrij' },
];

export function MotiesPage() {
  const [searchParams] = useSearchParams();
  const highlightMotieId = searchParams.get('motie');
  const [statusFilter, setStatusFilter] = useState<MotieImportStatus | 'all'>(
    highlightMotieId ? 'all' : 'imported'
  );
  const { data: imports, isLoading } = useMotieImports(
    statusFilter === 'all' ? undefined : { status: statusFilter }
  );
  const triggerImport = useTriggerMotieImport();

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          Beheer geïmporteerde moties uit de Tweede en Eerste Kamer.
        </p>
        <Button
          icon={<RefreshCw className={`h-4 w-4 ${triggerImport.isPending ? 'animate-spin' : ''}`} />}
          onClick={() => triggerImport.mutate()}
          disabled={triggerImport.isPending}
        >
          {triggerImport.isPending ? 'Importeren...' : 'Importeer nieuwe moties'}
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
          title="Geen moties gevonden"
          description={
            statusFilter === 'imported'
              ? 'Er zijn geen moties die beoordeeld moeten worden.'
              : 'Er zijn geen moties met deze status.'
          }
        />
      ) : (
        <div className="space-y-3">
          {imports.map((motie) => (
            <MotieReviewCard
              key={motie.id}
              motie={motie}
              defaultExpanded={motie.id === highlightMotieId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
