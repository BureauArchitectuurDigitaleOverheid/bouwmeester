import { useMemo } from 'react';
import { NodeCard } from './NodeCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useNodes } from '@/hooks/useNodes';
import { NodeType } from '@/types';

interface NodeListProps {
  enabledNodeTypes: Set<NodeType>;
  searchQuery: string;
}

export function NodeList({ enabledNodeTypes, searchQuery }: NodeListProps) {
  const { data: nodes, isLoading, error } = useNodes();

  const filteredNodes = useMemo(() => {
    if (!nodes) return undefined;
    const q = searchQuery.toLowerCase();
    return nodes.filter(
      (node) =>
        enabledNodeTypes.has(node.node_type) &&
        (!q || node.title.toLowerCase().includes(q) || node.description?.toLowerCase().includes(q)),
    );
  }, [nodes, enabledNodeTypes, searchQuery]);

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
