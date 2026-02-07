import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

export interface MultiSelectOption {
  value: string;
  label: string;
  color?: string;
}

interface MultiSelectProps {
  value: Set<string>;
  onChange: (value: Set<string>) => void;
  options: MultiSelectOption[];
  placeholder?: string;
  allLabel?: string;
}

export function MultiSelect({
  value,
  onChange,
  options,
  placeholder = 'Selecteer...',
  allLabel = 'Alles',
}: MultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const allSelected = options.length > 0 && options.every((o) => value.has(o.value));
  const noneSelected = options.every((o) => !value.has(o.value));
  const selectedCount = options.filter((o) => value.has(o.value)).length;

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleOption = (optValue: string) => {
    const next = new Set(value);
    if (next.has(optValue)) {
      next.delete(optValue);
    } else {
      next.add(optValue);
    }
    onChange(next);
  };

  const toggleAll = () => {
    if (allSelected) {
      onChange(new Set());
    } else {
      onChange(new Set(options.map((o) => o.value)));
    }
  };

  const displayLabel = allSelected || noneSelected
    ? allLabel
    : `${selectedCount} van ${options.length}`;

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center w-full rounded-xl border bg-white px-3.5 py-2.5 text-sm cursor-pointer transition-colors duration-150 border-border hover:border-border-hover ${
          isOpen ? 'ring-2 ring-primary-500/20 border-primary-500' : ''
        }`}
      >
        <span className={`flex-1 text-left truncate ${allSelected || noneSelected ? 'text-text-secondary/50' : 'text-text'}`}>
          {displayLabel}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-text-secondary shrink-0 ml-2 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <ul className="absolute z-50 mt-1 w-full max-h-60 overflow-auto rounded-xl border border-border bg-white shadow-lg py-1">
          {/* Select all / none */}
          <li
            onClick={toggleAll}
            className="px-3.5 py-2 text-sm cursor-pointer transition-colors hover:bg-gray-50 flex items-center gap-2 border-b border-border"
          >
            <div className={`h-3.5 w-3.5 rounded border flex items-center justify-center shrink-0 ${
              allSelected ? 'bg-primary-600 border-primary-600' : 'border-gray-300'
            }`}>
              {allSelected && <Check className="h-2.5 w-2.5 text-white" />}
            </div>
            <span className="font-medium text-text">{allLabel}</span>
          </li>

          {options.map((opt) => (
            <li
              key={opt.value}
              onClick={() => toggleOption(opt.value)}
              className="px-3.5 py-2 text-sm cursor-pointer transition-colors hover:bg-gray-50 flex items-center gap-2"
            >
              <div className={`h-3.5 w-3.5 rounded border flex items-center justify-center shrink-0 ${
                value.has(opt.value) ? 'bg-primary-600 border-primary-600' : 'border-gray-300'
              }`}>
                {value.has(opt.value) && <Check className="h-2.5 w-2.5 text-white" />}
              </div>
              {opt.color && (
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ background: opt.color }}
                />
              )}
              <span className="text-text">{opt.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
