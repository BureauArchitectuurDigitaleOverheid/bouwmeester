import { useState, useRef, useEffect, useMemo } from 'react';
import { Search as SearchIcon } from 'lucide-react';
import { useSearch } from '@/hooks/useSearch';
import {
  ALL_RESULT_TYPES,
  FilterChips,
  SearchResultsList,
  useResultNavigation,
} from '@/components/search/SearchResults';
import { usePermissions } from '@/hooks/usePermissions';
import { SEARCH_TYPE_PERMISSIONS, type SearchResultType } from '@/types';

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [activeTypes, setActiveTypes] = useState<SearchResultType[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const { hasPermission } = usePermissions();

  const allowedTypes = useMemo(
    () => ALL_RESULT_TYPES.filter((t) => hasPermission(SEARCH_TYPE_PERMISSIONS[t])),
    [hasPermission],
  );

  const filterTypes = activeTypes.length > 0 ? activeTypes : undefined;
  const { data, isLoading, isFetched } = useSearch(query, filterTypes);

  const handleResultClick = useResultNavigation();

  const toggleType = (type: SearchResultType) => {
    setActiveTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  };

  // Focus search input on "/" key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        document.activeElement !== inputRef.current &&
        !(document.activeElement instanceof HTMLInputElement) &&
        !(document.activeElement instanceof HTMLTextAreaElement) &&
        !(document.activeElement as HTMLElement)?.isContentEditable
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="text-sm text-text-secondary">
          Doorzoek alles: beleidscorpus, taken, personen, organisaties, parlementaire items, tags en leads.
        </p>
      </div>

      {/* Search input */}
      <div className="relative">
        <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-text-secondary" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Zoek op titel, naam, beschrijving, trefwoord..."
          autoFocus
          className="block w-full rounded-2xl border border-border bg-white pl-12 pr-4 py-3.5 text-sm text-text placeholder:text-text-secondary/50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 hover:border-border-hover shadow-sm"
        />
      </div>

      {/* Filter chips */}
      <FilterChips activeTypes={activeTypes} onToggle={toggleType} allowedTypes={allowedTypes} className="gap-2" />

      {/* Results */}
      <SearchResultsList
        query={query}
        data={data}
        isLoading={isLoading}
        isFetched={isFetched}
        onResultClick={handleResultClick}
      />
    </div>
  );
}
