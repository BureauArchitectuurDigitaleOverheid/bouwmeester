import { Fragment, useCallback, useRef } from 'react';
import DOMPurify from 'dompurify';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { richTextToPlain } from '@/utils/richtext';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import {
  SEARCH_RESULT_TYPE_LABELS,
  SEARCH_RESULT_TYPE_COLORS,
  NODE_TYPE_LABELS,
  NODE_STATUS_LABELS,
  TASK_STATUS_LABELS,
  formatOrganisatieType,
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
  parlementair_item: PARLEMENTAIR_TYPE_LABELS,
  lead: LEAD_STAGE_LABELS as Record<string, string>,
};

export function formatSubtitle(result: SearchResult): string | undefined {
  if (!result.subtitle) return undefined;
  if (result.result_type === 'person') {
    return formatFunctie(result.subtitle);
  }
  if (result.result_type === 'organisatie_eenheid') {
    return formatOrganisatieType(result.subtitle);
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
  allowedTypes?: SearchResultType[];
  className?: string;
}

export function FilterChips({ activeTypes, onToggle, allowedTypes, className = '' }: FilterChipsProps) {
  const visibleTypes = allowedTypes ?? ALL_RESULT_TYPES;
  const ref = useRef<HTMLElement>(null);

  // Each nldd-toggle-button fires its own `change` ({ selected, value }), which
  // bubbles to the group; `value` is the SearchResultType that was toggled.
  const handleChange = useCallback(
    (event: Event) => {
      const value = (event as CustomEvent<{ value?: string }>).detail?.value;
      if (value) onToggle(value as SearchResultType);
    },
    [onToggle],
  );
  useNlddEvent(ref, 'change', handleChange);

  return (
    <nldd-toggle-button-group ref={ref} type="checkbox" size="sm" className={className}>
      {visibleTypes.map((type) => (
        // `selected` means "you picked this one", so an empty filter leaves
        // every button unselected rather than marking them all. Treating "no
        // filter" as "all selected" painted the whole row solid and left no
        // visible difference once you actually chose a type.
        <nldd-toggle-button
          key={type}
          value={type}
          text={SEARCH_RESULT_TYPE_LABELS[type]}
          selected={orUndef(activeTypes.includes(type))}
        />
      ))}
    </nldd-toggle-button-group>
  );
}

/**
 * A single search hit inside the command-palette listbox.
 *
 * Rendered as an `nldd-list-item` option: the list's own search input drives
 * ArrowUp/Down/Home/End/Enter, and Enter triggers this row's inner action
 * (the button `onClick` below) without DOM focus ever leaving the input — see
 * `nldd-list type="listbox"` in list.js.
 */
export function ResultItem({ result, onClick }: { result: SearchResult; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);

  return (
    <nldd-list-item ref={ref} button size="md">
      <ResultItemContent result={result} compact />
    </nldd-list-item>
  );
}

function ResultItemContent({ result, compact }: { result: SearchResult; compact?: boolean }) {
  return (
    <div className="flex items-start gap-3 w-full">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <Badge variant={SEARCH_RESULT_TYPE_COLORS[result.result_type]} dot>
            {SEARCH_RESULT_TYPE_LABELS[result.result_type]}
          </Badge>
          {result.subtitle && (
            <span className="text-xs text-text-secondary">{formatSubtitle(result)}</span>
          )}
        </div>
        <h4 className="text-sm font-medium text-text">{result.title}</h4>
        {result.description && (
          <p className={`text-xs text-text-secondary mt-0.5 ${compact ? 'line-clamp-1' : 'line-clamp-2'}`}>
            {richTextToPlain(result.description)}
          </p>
        )}
        {result.highlights &&
          result.highlights.length > 0 &&
          (compact ? (
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
          ))}
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
}

/**
 * Full-page results (SearchPage): plain result cards, no listbox semantics.
 * The command-palette rendering for SearchModal's `nldd-list type="listbox"`
 * lives in `ResultItem` / `GroupedListboxRows` instead, since a listbox owns
 * its own search field and active-option handling that this page doesn't use.
 */
export function SearchResultsList({ query, data, isLoading, isFetched, onResultClick }: SearchResultsListProps) {
  const results = data?.results ?? [];
  const grouped = groupResults(results);

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  if (query.length >= 2 && isFetched && results.length === 0) {
    return (
      <EmptyState
        icon="question-mark-circle"
        title="Geen resultaten"
        description={`Geen resultaten gevonden voor "${query}". Probeer een andere zoekterm.`}
      />
    );
  }

  if (results.length > 0) {
    return (
      <div className="space-y-6">
        <p className="text-sm text-text-secondary">
          {data?.total ?? results.length} resultaten voor &ldquo;{data?.query ?? query}&rdquo;
        </p>
        {Object.entries(grouped).map(([resultType, groupResults]) => (
          <div key={resultType}>
            <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2 block">
              {SEARCH_RESULT_TYPE_LABELS[resultType as SearchResultType]} ({groupResults.length})
            </span>
            <div className="space-y-2">
              {groupResults.map((result) => (
                <ResultCard
                  key={`${result.result_type}-${result.id}`}
                  result={result}
                  onClick={() => onResultClick(result)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (query.length < 2 && !isFetched) {
    return (
      <div className="text-center py-12">
        <nldd-icon name="magnifier" size="40" style={{ opacity: 0.3 }} aria-hidden="true" />
        <p className="text-sm text-text-secondary mt-3">Voer minimaal 2 tekens in om te zoeken.</p>
      </div>
    );
  }

  return null;
}

function ResultCard({ result, onClick }: { result: SearchResult; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return (
    <nldd-card ref={ref} button>
      <ResultItemContent result={result} />
    </nldd-card>
  );
}

/**
 * Grouped rows for the command-palette listbox (SearchModal): a plain-text
 * group label between runs of `nldd-list-item` options, all inside the same
 * `nldd-list type="listbox"` so arrow-key navigation and the active option
 * span every group. `nldd-list` has no built-in group heading for listbox
 * rows, and its keyboard/active-option logic queries `:scope > nldd-list-item`
 * directly, so the label has to sit as a direct-child sibling of the items
 * rather than wrap them in a container div — that would hide them from it.
 */
export function GroupedListboxRows({
  results,
  onResultClick,
}: {
  results: SearchResult[];
  onResultClick: (result: SearchResult) => void;
}) {
  const grouped = groupResults(results);
  return (
    <>
      {Object.entries(grouped).map(([resultType, groupResults]) => (
        <Fragment key={resultType}>
          <div className="px-5 pt-3 pb-1" role="presentation">
            <span className="text-[10px] font-semibold text-text-secondary uppercase tracking-wider">
              {SEARCH_RESULT_TYPE_LABELS[resultType as SearchResultType]} ({groupResults.length})
            </span>
          </div>
          {groupResults.map((result) => (
            <ResultItem
              key={`${result.result_type}-${result.id}`}
              result={result}
              onClick={() => onResultClick(result)}
            />
          ))}
        </Fragment>
      ))}
    </>
  );
}
