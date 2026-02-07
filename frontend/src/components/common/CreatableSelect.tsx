import { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown, Plus } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
}

interface CreatableSelectProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  onCreate?: (text: string) => Promise<string | null>;
  createLabel?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
}

export function CreatableSelect({
  label,
  value,
  onChange,
  options,
  placeholder = 'Selecteer...',
  onCreate,
  createLabel = 'Nieuw aanmaken',
  error,
  disabled,
  required,
}: CreatableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const [isCreating, setIsCreating] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selectedOption = options.find((o) => o.value === value);

  const filtered = query
    ? options.filter(
        (o) =>
          o.label.toLowerCase().includes(query.toLowerCase()) ||
          o.description?.toLowerCase().includes(query.toLowerCase()),
      )
    : options;

  const showCreateOption =
    onCreate && query.trim() && !filtered.some((o) => o.label.toLowerCase() === query.trim().toLowerCase());

  const totalItems = filtered.length + (showCreateOption ? 1 : 0);

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Reset highlight when filtered list changes
  useEffect(() => {
    setHighlightedIndex(0);
  }, [query]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (isOpen && listRef.current) {
      const item = listRef.current.children[highlightedIndex] as HTMLElement | undefined;
      item?.scrollIntoView({ block: 'nearest' });
    }
  }, [highlightedIndex, isOpen]);

  const selectOption = useCallback(
    (opt: SelectOption) => {
      onChange(opt.value);
      setIsOpen(false);
      setQuery('');
    },
    [onChange],
  );

  const handleCreate = useCallback(async () => {
    if (!onCreate || !query.trim() || isCreating) return;
    setIsCreating(true);
    try {
      const newId = await onCreate(query.trim());
      if (newId) {
        onChange(newId);
      }
    } finally {
      setIsCreating(false);
      setIsOpen(false);
      setQuery('');
    }
  }, [onCreate, query, onChange, isCreating]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex((i) => (i + 1) % totalItems);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex((i) => (i - 1 + totalItems) % totalItems);
        break;
      case 'Enter':
        e.preventDefault();
        if (showCreateOption && highlightedIndex === filtered.length) {
          handleCreate();
        } else if (filtered[highlightedIndex]) {
          selectOption(filtered[highlightedIndex]);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setQuery('');
        break;
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    if (!isOpen) setIsOpen(true);
  };

  const handleToggle = () => {
    if (disabled) return;
    setIsOpen(!isOpen);
    if (!isOpen) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const selectId = label?.toLowerCase().replace(/\s+/g, '-');

  return (
    <div className="space-y-1.5" ref={containerRef}>
      {label && (
        <label htmlFor={selectId} className="block text-sm font-medium text-text">
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
      )}
      <div className="relative">
        {/* Trigger */}
        <div
          onClick={handleToggle}
          className={`flex items-center w-full rounded-xl border bg-white px-3.5 py-2.5 text-sm cursor-pointer transition-colors duration-150 ${
            error
              ? 'border-red-300 focus-within:ring-red-500/20 focus-within:border-red-500'
              : 'border-border hover:border-border-hover focus-within:ring-2 focus-within:ring-primary-500/20 focus-within:border-primary-500'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {isOpen ? (
            <input
              ref={inputRef}
              id={selectId}
              type="text"
              value={query}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              className="flex-1 outline-none bg-transparent text-text placeholder:text-text-secondary/50"
              placeholder={selectedOption?.label || placeholder}
              autoFocus
            />
          ) : (
            <span className={`flex-1 truncate ${selectedOption ? 'text-text' : 'text-text-secondary/50'}`}>
              {selectedOption?.label || placeholder}
            </span>
          )}
          <ChevronDown
            className={`h-4 w-4 text-text-secondary shrink-0 ml-2 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          />
        </div>

        {/* Dropdown */}
        {isOpen && (
          <ul
            ref={listRef}
            className="absolute z-50 mt-1 w-full max-h-60 overflow-auto rounded-xl border border-border bg-white shadow-lg py-1"
          >
            {filtered.length === 0 && !showCreateOption && (
              <li className="px-3.5 py-2.5 text-sm text-text-secondary">Geen resultaten</li>
            )}

            {filtered.map((opt, idx) => (
              <li
                key={opt.value}
                onClick={() => selectOption(opt)}
                onMouseEnter={() => setHighlightedIndex(idx)}
                className={`px-3.5 py-2 text-sm cursor-pointer transition-colors ${
                  highlightedIndex === idx ? 'bg-primary-50 text-primary-700' : 'text-text hover:bg-gray-50'
                } ${opt.value === value ? 'font-medium' : ''}`}
              >
                <div>{opt.label}</div>
                {opt.description && (
                  <div className="text-xs text-text-secondary mt-0.5">{opt.description}</div>
                )}
              </li>
            ))}

            {showCreateOption && (
              <li
                onClick={handleCreate}
                onMouseEnter={() => setHighlightedIndex(filtered.length)}
                className={`px-3.5 py-2 text-sm cursor-pointer transition-colors flex items-center gap-2 border-t border-border ${
                  highlightedIndex === filtered.length
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-primary-600 hover:bg-gray-50'
                } ${isCreating ? 'opacity-50 pointer-events-none' : ''}`}
              >
                <Plus className="h-3.5 w-3.5" />
                <span>
                  {createLabel}: &quot;{query.trim()}&quot;
                </span>
              </li>
            )}
          </ul>
        )}
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
