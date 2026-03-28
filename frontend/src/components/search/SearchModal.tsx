import { useState, useRef, useEffect } from 'react';
import { Search as SearchIcon } from 'lucide-react';
import { useSearch } from '@/hooks/useSearch';
import {
  FilterChips,
  SearchResultsList,
  groupResults,
  useResultNavigation,
} from './SearchResults';
import type { SearchResultType } from '@/types';

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
}

export function SearchModal({ open, onClose }: SearchModalProps) {
  const [query, setQuery] = useState('');
  const [activeTypes, setActiveTypes] = useState<SearchResultType[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const filterTypes = activeTypes.length > 0 ? activeTypes : undefined;
  const { data, isLoading, isFetched } = useSearch(query, filterTypes);

  const results = data?.results ?? [];
  const flatResults = Object.values(groupResults(results)).flat();

  const handleResultClick = useResultNavigation(onClose);

  const toggleType = (type: SearchResultType) => {
    setActiveTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  };

  // Focus input when modal opens, reset state
  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveTypes([]);
      setSelectedIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Lock body scroll while open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = '';
      };
    }
  }, [open]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, flatResults.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter' && flatResults[selectedIndex]) {
        e.preventDefault();
        handleResultClick(flatResults[selectedIndex]);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, flatResults, selectedIndex, onClose, handleResultClick]);

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0);
  }, [query, activeTypes]);

  // Scroll selected result into view
  useEffect(() => {
    if (!resultsRef.current) return;
    const selected = resultsRef.current.querySelector('[data-selected="true"]');
    selected?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative w-full max-w-2xl mx-4 bg-surface rounded-2xl shadow-2xl border border-border animate-in fade-in zoom-in-95 overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
          <SearchIcon className="h-5 w-5 text-text-secondary shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Zoek op titel, naam, beschrijving, trefwoord..."
            className="flex-1 text-sm text-text placeholder:text-text-secondary/50 bg-transparent outline-none"
          />
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 rounded bg-gray-100 text-[10px] font-medium text-text-secondary">
            Esc
          </kbd>
        </div>

        {/* Filter chips */}
        <div className="border-b border-border px-5 py-3">
          <FilterChips activeTypes={activeTypes} onToggle={toggleType} />
        </div>

        {/* Results */}
        <div ref={resultsRef} className="max-h-[50vh] overflow-y-auto">
          <SearchResultsList
            query={query}
            data={data}
            isLoading={isLoading}
            isFetched={isFetched}
            onResultClick={handleResultClick}
            selectedIndex={selectedIndex}
            compact
          />
        </div>
      </div>
    </div>
  );
}
