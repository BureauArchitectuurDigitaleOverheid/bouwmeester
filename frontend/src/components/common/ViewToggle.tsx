import { useCallback, useRef, type ReactNode } from 'react';
import { eventValue, orUndef, useNlddEvent } from '@/components/nldd/events';

export interface ViewToggleOption<T extends string> {
  value: T;
  label: string;
  /** An nldd-icon name. A ReactNode is still accepted from unconverted callers. */
  icon: ReactNode | string;
}

interface ViewToggleProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: ViewToggleOption<T>[];
}

/**
 * `nldd-segmented-control` behind the previous API.
 *
 * This is what that component is for: one choice out of a few, laid out as a
 * strip. It brings the radio semantics and the arrow-key behaviour, which the
 * hand-rolled row of buttons did not have — those were seven plain buttons with
 * no indication that they belonged together or that only one could be active.
 */
export function ViewToggle<T extends string>({ value, onChange, options }: ViewToggleProps<T>) {
  const ref = useRef<HTMLElement>(null);

  const handleChange = useCallback(
    (event: Event) => {
      const next = eventValue(event);
      if (next) onChange(next as T);
    },
    [onChange],
  );
  useNlddEvent(ref, 'change', handleChange);

  return (
    <nldd-segmented-control ref={ref} type="radio" size="sm" value={value}>
      {options.map((option) => (
        <nldd-segmented-control-item
          key={option.value}
          value={option.value}
          text={option.label}
          selected={orUndef(option.value === value)}
          {...(typeof option.icon === 'string' ? { icon: option.icon } : {})}
        >
          {/* A non-string icon is a leftover element from a caller that has not
              been converted; it still renders through the icon slot. */}
          {option.icon && typeof option.icon !== 'string' ? (
            <span slot="icon">{option.icon}</span>
          ) : null}
        </nldd-segmented-control-item>
      ))}
    </nldd-segmented-control>
  );
}
