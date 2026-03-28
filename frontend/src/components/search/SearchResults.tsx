import DOMPurify from 'dompurify';
import { FileQuestion, Search as SearchIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { richTextToPlain } from '@/utils/richtext';
import {
  SEARCH_RESULT_TYPE_LABELS,
  SEARCH_RESULT_TYPE_COLORS,
  NODE_TYPE_LABELS,
  NODE_STATUS_LABELS,
  TASK_STATUS_LABELS,
  ORGANISATIE_TYPE_LABELS,
  PARLEMENTAIR_TYPE_LABELS,
  LEAD_STAGE_LABELS,
  formatFunctie,
  type SearchResultType,
  type SearchResult,
  type SearchResponse,
} from '@/types';

export const ALL_RESULT_TYPES: SearchResultType[] = [
  'corpus_node',
  'task',
  'person',
  'organisatie_eenheid',
  'parlementair_item',
  'tag',
  'lead',
];

const SUBTITLE_LABEL_MAPS: Partial<
  Record<SearchResultType, Record<string, string>>
> = {
  corpus_node: { ...NODE_TYPE_LABELS, ...NODE_STATUS_LABELS },
  task: TASK_STATUS_LABELS,
  organisatie_eenheid: ORGANISATIE_TYPE_LABELS,
  parlementair_item: PARLEMENTAIR_TYPE_LABELS,
  lead: LEAD_STAGE_LABELS as Record<string, string>,
};

export function formatSubtitle(result: SearchResult): string | undefined {
  if (!result.subtitle) return undefined;
  if (result.result_type === 'person') {
    return formatFunctie(result.subtitle);
  }
  const map = SUBTITLE_LABEL_MAPS[result.result_type];
  return map?.[result.subtitle] ?? result.subtitle;
}

export function groupResults(results: SearchResult[]) {
  return results.reduce(
    (groups, result) => {
      const key = result.result_type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(result);
      return groups;
    },
    {} as Record<string, SearchResult[]>,
  );
}

export function useResultNavigation(onNavigated?: () => void) {
  const navigate = useNavigate();
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();
  const { openLeadDetail } = useLeadDetail();

  return (result: SearchResult) => {
    onNavigated?.();
    if (result.result_type === 'corpus_node') {
      openNodeDetail(result.id);
    } else if (result.result_type === 'task') {
      openTaskDetail(result.id);
    } else if (result.result_type === 'lead') {
      openLeadDetail(result.id);
    } else {
      navigate(result.url);
    }
  };
}

interface FilterChipsProps {
  activeTypes: SearchResultType[];
  onToggle: (type: SearchResultType) => void;
  className?: string;
}

export function FilterChips({ activeTypes, onToggle, className = '' }: FilterChipsProps) {
  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      {ALL_RESULT_TYPES.map((type) => {
        const isActive = activeTypes.length === 0 || activeTypes.includes(type);
        return (
          <button
            key={type}
            onClick={() => onToggle(type)}
            className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-colors duration-150 ${
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
  );
}

interface ResultItemProps {
  result: SearchResult;
  selected?: boolean;
  compact?: boolean;
  onClick: () => void;
}

export function ResultItem({ result, selected, compact, onClick }: ResultItemProps) {
  if (compact) {
    return (
      <button
        data-selected={selected}
        onClick={onClick}
        className={`w-full text-left px-5 py-2.5 transition-colors ${
          selected ? 'bg-primary-50' : 'hover:bg-gray-50'
        }`}
      >
        <ResultItemContent result={result} compact />
      </button>
    );
  }
  return null;
}

function ResultItemContent({ result, compact }: { result: SearchResult; compact?: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
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
          <p className={`text-xs text-text-secondary mt-0.5 ${compact ? 'line-clamp-1' : 'line-clamp-2'}`}>
            {richTextToPlain(result.description)}
          </p>
        )}
        {result.highlights && result.highlights.length > 0 && (
          compact ? (
            <p
              className="text-xs text-text-secondary mt-0.5 italic line-clamp-1"
              dangerouslySetInnerHTML={{
                __html: DOMPurify.sanitize(result.highlights[0], {
                  ALLOWED_TAGS: ['mark'],
                }),
              }}
            />
          ) : (
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
          )
        )}
      </div>
      {result.score > 0 && (
        <span className="text-xs text-text-secondary shrink-0">
          {Math.round(result.score * 100)}%
        </span>
      )}
    </div>
  );
}

interface SearchResultsListProps {
  query: string;
  data: SearchResponse | undefined;
  isLoading: boolean;
  isFetched: boolean;
  onResultClick: (result: SearchResult) => void;
  /** For modal: keyboard-selected index */
  selectedIndex?: number;
  /** For modal: render compact items without Card wrapper */
  compact?: boolean;
}

export function SearchResultsList({
  query,
  data,
  isLoading,
  isFetched,
  onResultClick,
  selectedIndex,
  compact,
}: SearchResultsListProps) {
  const results = data?.results ?? [];
  const grouped = groupResults(results);

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  if (query.length >= 2 && isFetched && results.length === 0) {
    if (compact) {
      return (
        <div className="flex flex-col items-center py-10 text-text-secondary">
          <FileQuestion className="h-10 w-10 mb-2 opacity-40" />
          <p className="text-sm">Geen resultaten voor &ldquo;{query}&rdquo;</p>
        </div>
      );
    }
    return (
      <EmptyState
        icon={<FileQuestion className="h-16 w-16" />}
        title="Geen resultaten"
        description={`Geen resultaten gevonden voor "${query}". Probeer een andere zoekterm.`}
      />
    );
  }

  if (results.length > 0) {
    let resultIndex = 0;
    return (
      <div className={compact ? 'py-2' : 'space-y-6'}>
        {!compact && (
          <p className="text-sm text-text-secondary">
            {data?.total ?? results.length} resultaten voor &ldquo;{data?.query ?? query}&rdquo;
          </p>
        )}
        {Object.entries(grouped).map(([resultType, groupResults]) => (
          <div key={resultType}>
            <div className={compact ? 'px-5 pt-3 pb-1' : ''}>
              <span className={`text-xs font-semibold text-text-secondary uppercase tracking-wider ${compact ? 'text-[10px]' : 'mb-2 block'}`}>
                {SEARCH_RESULT_TYPE_LABELS[resultType as SearchResultType]} ({groupResults.length})
              </span>
            </div>
            <div className={compact ? '' : 'space-y-2'}>
              {groupResults.map((result) => {
                const currentIndex = resultIndex++;
                const isSelected = selectedIndex !== undefined && currentIndex === selectedIndex;
                if (compact) {
                  return (
                    <ResultItem
                      key={`${result.result_type}-${result.id}`}
                      result={result}
                      selected={isSelected}
                      compact
                      onClick={() => onResultClick(result)}
                    />
                  );
                }
                return (
                  <div
                    key={`${result.result_type}-${result.id}`}
                    className="group bg-surface rounded-xl border border-border shadow-sm overflow-hidden hover:shadow-md hover:border-border-hover transition-all duration-200 cursor-pointer px-3 py-3 sm:px-5 sm:py-4"
                    onClick={() => onResultClick(result)}
                  >
                    <ResultItemContent result={result} />
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (query.length < 2 && !isFetched) {
    if (compact) {
      return (
        <div className="flex flex-col items-center py-10 text-text-secondary">
          <SearchIcon className="h-10 w-10 mb-2 opacity-20" />
          <p className="text-sm">Voer minimaal 2 tekens in om te zoeken.</p>
        </div>
      );
    }
    return (
      <div className="text-center py-12 text-text-secondary">
        <SearchIcon className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Voer minimaal 2 tekens in om te zoeken.</p>
      </div>
    );
  }

  return null;
}
