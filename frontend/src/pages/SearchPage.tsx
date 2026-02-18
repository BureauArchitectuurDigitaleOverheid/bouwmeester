import { useState } from 'react';
import DOMPurify from 'dompurify';
import { Search as SearchIcon, FileQuestion } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useSearch } from '@/hooks/useSearch';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { richTextToPlain } from '@/utils/richtext';
import {
  SEARCH_RESULT_TYPE_LABELS,
  SEARCH_RESULT_TYPE_COLORS,
  NODE_TYPE_LABELS,
  NODE_STATUS_LABELS,
  TASK_STATUS_LABELS,
  ORGANISATIE_TYPE_LABELS,
  PARLEMENTAIR_TYPE_LABELS,
  formatFunctie,
  type SearchResultType,
  type SearchResult,
} from '@/types';

const SUBTITLE_LABEL_MAPS: Partial<
  Record<SearchResultType, Record<string, string>>
> = {
  corpus_node: { ...NODE_TYPE_LABELS, ...NODE_STATUS_LABELS },
  task: TASK_STATUS_LABELS,
  organisatie_eenheid: ORGANISATIE_TYPE_LABELS,
  parlementair_item: PARLEMENTAIR_TYPE_LABELS,
};

function formatSubtitle(result: SearchResult): string | undefined {
  if (!result.subtitle) return undefined;
  if (result.result_type === 'person') {
    return formatFunctie(result.subtitle);
  }
  const map = SUBTITLE_LABEL_MAPS[result.result_type];
  return map?.[result.subtitle] ?? result.subtitle;
}

const ALL_RESULT_TYPES: SearchResultType[] = [
  'corpus_node',
  'task',
  'person',
  'organisatie_eenheid',
  'parlementair_item',
  'tag',
];

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [activeTypes, setActiveTypes] = useState<SearchResultType[]>([]);
  const navigate = useNavigate();
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();

  const filterTypes = activeTypes.length > 0 ? activeTypes : undefined;
  const { data, isLoading, isFetched } = useSearch(query, filterTypes);

  const results = data?.results ?? [];

  const toggleType = (type: SearchResultType) => {
    setActiveTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  };

  // Group results by result_type
  const grouped = results.reduce(
    (groups, result) => {
      const key = result.result_type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(result);
      return groups;
    },
    {} as Record<string, SearchResult[]>,
  );

  const handleResultClick = (result: SearchResult) => {
    if (result.result_type === 'corpus_node') {
      openNodeDetail(result.id);
    } else if (result.result_type === 'task') {
      openTaskDetail(result.id);
    } else {
      navigate(result.url);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="text-sm text-text-secondary">
          Doorzoek alles: beleidscorpus, taken, personen, organisaties, parlementaire items en tags.
        </p>
      </div>

      {/* Search input */}
      <div className="relative">
        <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-text-secondary" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Zoek op titel, naam, beschrijving, trefwoord..."
          autoFocus
          className="block w-full rounded-2xl border border-border bg-white pl-12 pr-4 py-3.5 text-sm text-text placeholder:text-text-secondary/50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 hover:border-border-hover shadow-sm"
        />
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        {ALL_RESULT_TYPES.map((type) => {
          const isActive = activeTypes.length === 0 || activeTypes.includes(type);
          return (
            <button
              key={type}
              onClick={() => toggleType(type)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors duration-150 ${
                isActive
                  ? 'bg-primary-50 border-primary-300 text-primary-700'
                  : 'bg-white border-border text-text-secondary hover:border-border-hover'
              }`}
            >
              {SEARCH_RESULT_TYPE_LABELS[type]}
            </button>
          );
        })}
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

          {Object.entries(grouped).map(([resultType, groupResults]) => (
            <div key={resultType}>
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                {SEARCH_RESULT_TYPE_LABELS[resultType as SearchResultType]} ({groupResults.length})
              </h3>
              <div className="space-y-2">
                {groupResults.map((result) => (
                  <Card
                    key={`${result.result_type}-${result.id}`}
                    hoverable
                    onClick={() => handleResultClick(result)}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge
                            variant={SEARCH_RESULT_TYPE_COLORS[result.result_type]}
                            dot
                          >
                            {SEARCH_RESULT_TYPE_LABELS[result.result_type]}
                          </Badge>
                          {result.subtitle && (
                            <span className="text-xs text-text-secondary">
                              {formatSubtitle(result)}
                            </span>
                          )}
                        </div>
                        <h4 className="text-sm font-medium text-text">
                          {result.title}
                        </h4>
                        {result.description && (
                          <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">
                            {richTextToPlain(result.description)}
                          </p>
                        )}
                        {result.highlights && result.highlights.length > 0 && (
                          <div className="mt-1.5 space-y-0.5">
                            {result.highlights.map((h, i) => (
                              <p
                                key={i}
                                className="text-xs text-text-secondary italic"
                                dangerouslySetInnerHTML={{
                                  __html: DOMPurify.sanitize(h, {
                                    ALLOWED_TAGS: ['mark'],
                                  }),
                                }}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                      {result.score > 0 && (
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
