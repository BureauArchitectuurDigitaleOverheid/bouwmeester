import { useCallback, useRef, type ReactNode } from 'react';
import { eventValue, orUndef, useNlddEvent } from '@/components/nldd/events';

export interface ViewToggleOption<T extends string> {
  value: T;
  label: string;
  /**
   * An `<Icon />` element, which is what all eleven call sites pass today, or
   * a bare nldd-icon name.
   *
   * The name is the shorter route: `nldd-segmented-control-item` has its own
   * `icon` attribute, and these call sites already use real design-system
   * names, so `icon: 'list'` skips the wrapper entirely.
   */
  icon: ReactNode | string;
}

interface ViewToggleProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: ViewToggleOption<T>[];
  /** Names the group itself; the items only name the options inside it. */
  accessibleLabel?: string;
}

/**
 * One choice out of a few, laid out as a strip.
 *
 * `nldd-segmented-control` brings the radio semantics and the arrow-key
 * behaviour. A row of plain buttons gives a screen reader no indication that
 * they belong together or that only one can be active, so use this instead.
 *
 * The group carries a name of its own: a radiogroup without one is announced
 * as an unnamed set of options, so the listener hears "Bord, selected" with
 * nothing saying what is being chosen. Every call site today picks a view, so
 * that is the default; pass `accessibleLabel` where the choice is something
 * else.
 */
export function ViewToggle<T extends string>({
  value,
  onChange,
  options,
  accessibleLabel = 'Weergave',
}: ViewToggleProps<T>) {
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
    <nldd-segmented-control
      ref={ref}
      type="radio"
      size="sm"
      value={value}
      accessible-label={accessibleLabel}
    >
      {options.map((option) => (
        <nldd-segmented-control-item
          key={option.value}
          value={option.value}
          text={option.label}
          selected={orUndef(option.value === value)}
          {...(typeof option.icon === 'string' ? { icon: option.icon } : {})}
        >
          {/* A non-string icon renders through the icon slot instead of the
              `icon` attribute. */}
          {option.icon && typeof option.icon !== 'string' ? (
            <span slot="icon">{option.icon}</span>
          ) : null}
        </nldd-segmented-control-item>
      ))}
    </nldd-segmented-control>
  );
}
