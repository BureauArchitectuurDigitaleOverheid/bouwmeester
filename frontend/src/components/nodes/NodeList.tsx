import { useMemo, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search } from 'lucide-react';
import { NodeCard } from './NodeCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { Input } from '@/components/common/Input';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useNodes } from '@/hooks/useNodes';
import { NodeType } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { useVocabulary } from '@/contexts/VocabularyContext';

export function NodeList() {
  const { nodeLabel } = useVocabulary();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedType = searchParams.get('type') ?? '';
  const searchQuery = searchParams.get('q') ?? '';

  const setSelectedType = useCallback((value: string) => {
    setSearchParams((prev) => {
      if (value) prev.set('type', value); else prev.delete('type');
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const setSearchQuery = useCallback((value: string) => {
    setSearchParams((prev) => {
      if (value) prev.set('q', value); else prev.delete('q');
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const nodeTypeOptions: SelectOption[] = [
    { value: '', label: 'Alle types' },
    ...Object.values(NodeType).map((t) => ({
      value: t,
      label: nodeLabel(t),
    })),
  ];
  const nodeType = selectedType || undefined;
  const { data: nodes, isLoading, error } = useNodes(nodeType as NodeType | undefined);

  const filteredNodes = useMemo(() => {
    if (!nodes) return undefined;
    if (!searchQuery) return nodes;
    const q = searchQuery.toLowerCase();
    return nodes.filter(
      (node) =>
        node.title.toLowerCase().includes(q) ||
        node.description?.toLowerCase().includes(q),
    );
  }, [nodes, searchQuery]);

  if (error) {
    return (
      <EmptyState
        title="Fout bij laden"
        description="Er is een fout opgetreden bij het laden van de nodes. Probeer het opnieuw."
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="w-44">
          <CreatableSelect
            value={selectedType}
            onChange={setSelectedType}
            options={nodeTypeOptions}
            placeholder="Alle types"
          />
        </div>

        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value as string)}
            placeholder="Zoek in lijst..."
            className="pl-9"
          />
        </div>
      </div>

      {/* Grid */}
      {isLoading ? (
        <LoadingSpinner className="py-12" />
      ) : filteredNodes && filteredNodes.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredNodes.map((node) => (
            <NodeCard key={node.id} node={node} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="Geen nodes gevonden"
          description={
            searchQuery
              ? `Geen resultaten voor "${searchQuery}". Pas de zoekterm of filter aan.`
              : 'Er zijn nog geen nodes van dit type. Maak een nieuwe node aan.'
          }
        />
      )}
    </div>
  );
}
