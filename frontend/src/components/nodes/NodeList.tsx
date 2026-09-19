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
    <nldd-container gap="16">
      {isLoading ? (
        <LoadingSpinner className="py-12" />
      ) : filteredNodes && filteredNodes.length > 0 ? (
        <nldd-container layout="grid" gap="16">
          {filteredNodes.map((node) => (
            <NodeCard key={node.id} node={node} />
          ))}
        </nldd-container>
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
    </nldd-container>
  );
}
