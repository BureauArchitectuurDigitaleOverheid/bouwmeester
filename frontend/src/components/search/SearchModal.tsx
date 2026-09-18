import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useSearch } from '@/hooks/useSearch';
import { usePermissions } from '@/hooks/usePermissions';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import {
  ALL_RESULT_TYPES,
  FilterChips,
  GroupedListboxRows,
  useResultNavigation,
} from './SearchResults';
import { SEARCH_TYPE_PERMISSIONS, type SearchResultType } from '@/types';

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Command palette, opened with "/". Rendered at the document root by
 * AppLayout, deliberately outside the split view (rule: overlays never sit as
 * a light-DOM sibling of the split view or they get slotted into the main
 * pane).
 *
 * `nldd-list type="listbox"` owns the search field, ArrowUp/Down/Home/End,
 * Enter-to-activate and Escape-to-clear-then-close itself (see list.js): when
 * the search value is empty, Escape falls through instead of being consumed,
 * which is what lets this component's own Escape handler close the modal.
 * That replaced this component's hand-rolled input, selectedIndex state and
 * keydown listener entirely.
 */
export function SearchModal({ open, onClose }: SearchModalProps) {
  const [query, setQuery] = useState('');
  const [activeTypes, setActiveTypes] = useState<SearchResultType[]>([]);
  const listRef = useRef<HTMLElement>(null);
  const { hasPermission } = usePermissions();

  const allowedTypes = useMemo(
    () => ALL_RESULT_TYPES.filter((t) => hasPermission(SEARCH_TYPE_PERMISSIONS[t])),
    [hasPermission],
  );

  const filterTypes = activeTypes.length > 0 ? activeTypes : undefined;
  const { data, isLoading } = useSearch(query, filterTypes);
  const results = data?.results ?? [];

  const handleResultClick = useResultNavigation(onClose);

  const toggleType = useCallback((type: SearchResultType) => {
    setActiveTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]));
  }, []);

  const handleSearchInput = useCallback((e: Event) => setQuery(eventValue(e)), []);
  useNlddEvent(listRef, 'input', handleSearchInput);

  // Reset state and focus the listbox's own search field when the modal opens.
  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveTypes([]);
      requestAnimationFrame(() => {
        const input = listRef.current?.shadowRoot?.querySelector('input');
        input?.focus();
      });
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

  // The listbox consumes Escape itself to clear a non-empty search value; only
  // an Escape on an already-empty field reaches here, closing the modal.
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      {/* Overlay */}
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />

      {/* Dialog */}
      <div className="relative w-full max-w-2xl mx-4 rounded-2xl shadow-2xl overflow-hidden">
        <nldd-list
          ref={listRef}
          type="listbox"
          variant="box-base"
          height="50vh"
          accessible-label="Zoeken"
        >
          <div slot="toolbar" className="px-5 pb-3">
            <FilterChips activeTypes={activeTypes} onToggle={toggleType} allowedTypes={allowedTypes} />
          </div>

          {/* Zero rows always routes here (never `no-results`, which is only for
              rows hidden by client-side filtering — this search is server-driven
              and simply renders nothing while there are no hits). */}
          {isLoading ? (
            <nldd-inline-dialog slot="empty" variant="loading" text="Zoeken..." />
          ) : query.length < 2 ? (
            <nldd-inline-dialog slot="empty" text="Voer minimaal 2 tekens in om te zoeken." />
          ) : (
            <nldd-inline-dialog slot="empty" text={`Geen resultaten voor "${query}"`} />
          )}

          {!isLoading && <GroupedListboxRows results={results} onResultClick={handleResultClick} />}
        </nldd-list>
      </div>
    </div>
  );
}
