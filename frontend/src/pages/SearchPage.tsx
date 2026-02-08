import { useState } from 'react';
import { Search as SearchIcon, FileQuestion } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useSearch } from '@/hooks/useSearch';
import { NODE_TYPE_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

export function SearchPage() {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const { nodeLabel, nodeAltLabel } = useVocabulary();
  const { data, isLoading, isFetched } = useSearch(query);

  const results = data?.results ?? [];

  // Group by node type
  const grouped = results.reduce(
    (groups, result) => {
      const key = result.node_type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(result);
      return groups;
    },
    {} as Record<string, typeof results>,
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="text-sm text-text-secondary">
          Doorzoek het volledige corpus op trefwoord.
        </p>
      </div>

      {/* Search input */}
      <div className="relative">
        <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-text-secondary" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Zoek op titel, beschrijving, trefwoord..."
          autoFocus
          className="block w-full rounded-2xl border border-border bg-white pl-12 pr-4 py-3.5 text-sm text-text placeholder:text-text-secondary/50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 hover:border-border-hover shadow-sm"
        />
      </div>

      {/* Results */}
      {isLoading && <LoadingSpinner className="py-8" />}

      {!isLoading && query.length >= 2 && isFetched && results.length === 0 && (
        <EmptyState
          icon={<FileQuestion className="h-16 w-16" />}
          title="Geen resultaten"
          description={`Geen resultaten gevonden voor "${query}". Probeer een andere zoekterm.`}
        />
      )}

      {!isLoading && results.length > 0 && (
        <div className="space-y-6">
          <p className="text-sm text-text-secondary">
            {data?.total ?? results.length} resultaten voor &ldquo;{data?.query ?? query}&rdquo;
          </p>

          {Object.entries(grouped).map(([nodeType, groupResults]) => (
            <div key={nodeType}>
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                {nodeLabel(nodeType)} (
                {groupResults.length})
              </h3>
              <div className="space-y-2">
                {groupResults.map((result) => (
                  <Card
                    key={result.id}
                    hoverable
                    onClick={() => navigate(`/nodes/${result.id}`)}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge
                            variant={
                              NODE_TYPE_COLORS[
                                result.node_type as keyof typeof NODE_TYPE_COLORS
                              ] as 'blue'
                            }
                            dot
                          >
                            {nodeLabel(result.node_type)}
                          </Badge>
                        </div>
                        <h4 className="text-sm font-medium text-text">
                          {result.title}
                        </h4>
                        {result.description && (
                          <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">
                            {result.description}
                          </p>
                        )}
                        {result.highlights && result.highlights.length > 0 && (
                          <div className="mt-1.5 space-y-0.5">
                            {result.highlights.map((h, i) => (
                              <p
                                key={i}
                                className="text-xs text-text-secondary italic"
                                dangerouslySetInnerHTML={{ __html: h }}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                      {result.score && (
                        <span className="text-xs text-text-secondary shrink-0">
                          {Math.round(result.score * 100)}%
                        </span>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Initial state */}
      {!isLoading && query.length < 2 && !isFetched && (
        <div className="text-center py-12 text-text-secondary">
          <SearchIcon className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm">Voer minimaal 2 tekens in om te zoeken.</p>
        </div>
      )}
    </div>
  );
}
