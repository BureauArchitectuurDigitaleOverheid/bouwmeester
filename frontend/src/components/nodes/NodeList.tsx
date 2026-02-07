import { useState } from 'react';
import { clsx } from 'clsx';
import { Search } from 'lucide-react';
import { NodeCard } from './NodeCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { Input } from '@/components/common/Input';
import { useNodes } from '@/hooks/useNodes';
import { NodeType, NODE_TYPE_LABELS } from '@/types';

const allNodeTypes = [undefined, ...Object.values(NodeType)] as const;

export function NodeList() {
  const [selectedType, setSelectedType] = useState<NodeType | undefined>(undefined);
  const [searchQuery, setSearchQuery] = useState('');
  const { data: nodes, isLoading, error } = useNodes(selectedType);

  const filteredNodes = nodes?.filter((node) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      node.title.toLowerCase().includes(q) ||
      node.description?.toLowerCase().includes(q)
    );
  });

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
      {/* Filter tabs */}
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {allNodeTypes.map((type) => (
          <button
            key={type ?? 'all'}
            onClick={() => setSelectedType(type)}
            className={clsx(
              'px-3.5 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all duration-150',
              selectedType === type
                ? 'bg-primary-900 text-white shadow-sm'
                : 'text-text-secondary hover:bg-gray-100 hover:text-text',
            )}
          >
            {type ? NODE_TYPE_LABELS[type] : 'Alles'}
          </button>
        ))}
      </div>

      {/* Search within list */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Zoek in lijst..."
          className="pl-9"
        />
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
