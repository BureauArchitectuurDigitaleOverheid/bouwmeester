import { clsx } from 'clsx';
import type { ReactNode } from 'react';

export interface ViewToggleOption<T extends string> {
  value: T;
  label: string;
  icon: ReactNode;
}

interface ViewToggleProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: ViewToggleOption<T>[];
}

export function ViewToggle<T extends string>({
  value,
  onChange,
  options,
}: ViewToggleProps<T>) {
  return (
    <div className="flex items-center bg-gray-100 rounded-xl p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          className={clsx(
            'flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-150',
            value === option.value
              ? 'bg-white text-text shadow-sm'
              : 'text-text-secondary hover:text-text',
          )}
        >
          {option.icon}
          <span className="hidden sm:inline">{option.label}</span>
        </button>
      ))}
    </div>
  );
}
