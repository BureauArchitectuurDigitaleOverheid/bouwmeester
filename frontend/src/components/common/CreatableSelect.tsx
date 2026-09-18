import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '@/api/client';
import { eventValue, useNlddEvent } from '@/components/nldd/events';

function extractCreateErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) {
      return 'Geen rechten om dit aan te maken.';
    }
    const body = err.body as Record<string, unknown> | undefined;
    if (body && typeof body.detail === 'string') return body.detail;
    return `Aanmaken niet gelukt (${err.status})`;
  }
  if (err instanceof Error && err.message) return err.message;
  return 'Aanmaken niet gelukt';
}

/** Id linking the input's `unmet` to the validation item that explains it. */
const MESSAGE_ID = 'creatable-select-message';

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
  /** Called when the search query changes (for API-driven filtering) */
  onQueryChange?: (query: string) => void;
  /**
   * When false, skip client-side filtering — show options as-is.
   * Use this when options are already filtered by an API call.
   * @default true
   */
  filterLocally?: boolean;
  /** Text to display when no option is selected (e.g. after creating a new item) */
  displayValue?: string;
  /** Called when the user clears the selection. */
  onClear?: () => void;
  /** Message to show when the dropdown is open but has no results */
  emptyMessage?: string;
  /** When false, hide the search input and show a plain dropdown. @default true */
  searchable?: boolean;
}

/**
 * `nldd-combo-box` behind the previous API.
 *
 * This replaces ~345 lines of hand-rolled autocomplete: the element owns the
 * filtering UI, the keyboard (arrows, Home/End, Enter, Escape), the ARIA
 * combobox wiring and the clear button.
 *
 * What stays ours is the one thing the element has no opinion about: creating an
 * option that does not exist yet. `allow-custom` lets a typed value be
 * committed, and the `change` handler below decides whether that value is an
 * existing option or a new one to POST.
 *
 * `searchable={false}` still renders a combo box. The element has no read-only
 * list mode, and swapping in an `nldd-dropdown` would change the keyboard
 * behaviour between call sites that look identical — a mode, in the sense the
 * design guidelines warn about. Typing simply filters, which is not harmful.
 */
export function CreatableSelect({
  label,
  value,
  onChange,
  options,
  placeholder = 'Selecteer...',
  onCreate,
  createLabel,
  error,
  disabled,
  required,
  onQueryChange,
  filterLocally = true,
  displayValue,
  onClear,
  emptyMessage = 'Geen resultaten',
  // The element has no read-only list mode. Typing filters the menu, which is
  // harmless, and swapping in an nldd-dropdown here would make two call sites
  // that look identical behave differently — a mode, in the sense the design
  // guidelines warn against. Accepted for API compatibility, intentionally unused.
  searchable: _searchable = true,
}: CreatableSelectProps) {
  const ref = useRef<HTMLElement>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [query, setQuery] = useState('');

  const selected = options.find((o) => o.value === value);
  // `text` is what the input shows; it differs from `value` (an id) and has to
  // be set explicitly when populating an existing record.
  const text = selected?.label ?? displayValue ?? '';

  const visible =
    filterLocally && query
      ? options.filter(
          (o) =>
            o.label.toLowerCase().includes(query.toLowerCase()) ||
            o.description?.toLowerCase().includes(query.toLowerCase()),
        )
      : options;

  // Keep the element's own text in step when the selection changes elsewhere.
  useEffect(() => {
    const el = ref.current as (HTMLElement & { text?: string }) | null;
    if (el && el.text !== text) el.text = text;
  }, [text]);

  const handleInput = useCallback(
    (event: Event) => {
      const next = eventValue(event);
      setQuery(next);
      onQueryChange?.(next);
      if (next === '' && value && onClear) onClear();
    },
    [onQueryChange, onClear, value],
  );

  const handleChange = useCallback(
    async (event: Event) => {
      const committed = eventValue(event);
      setCreateError(null);

      // An existing option: commit its id.
      const match = options.find((o) => o.value === committed || o.label === committed);
      if (match) {
        onChange(match.value);
        setQuery('');
        return;
      }

      if (!committed) {
        onClear?.();
        return;
      }

      // Anything else is a new value the user typed. Only create when the caller
      // supports it; otherwise ignore, so a typo cannot silently clear a field.
      if (!onCreate) return;

      setIsCreating(true);
      try {
        const created = await onCreate(committed);
        if (created) {
          onChange(created);
          setQuery('');
        }
      } catch (err) {
        setCreateError(extractCreateErrorMessage(err));
      } finally {
        setIsCreating(false);
      }
    },
    [options, onChange, onCreate, onClear],
  );

  useNlddEvent(ref, 'input', handleInput);
  useNlddEvent(ref, 'change', handleChange);

  const message = createError ?? error;

  const comboBox = (
    <nldd-combo-box
      ref={ref}
      value={value}
      text={text}
      placeholder={placeholder}
      max-items={8}
      {...(onCreate ? { 'allow-custom': true } : {})}
      {...(disabled || isCreating ? { disabled: true } : {})}
      {...(required ? { required: true } : {})}
      {...(message ? { invalid: true, unmet: MESSAGE_ID } : {})}
      {...(label ? {} : { 'accessible-label': placeholder })}
    >
      <nldd-menu>
        {visible.map((option) => (
          <nldd-menu-item
            key={option.value}
            value={option.value}
            text={option.label}
            {...(option.description ? { details: option.description } : {})}
          />
        ))}
        {visible.length === 0 && (
          <nldd-menu-item value="" text={emptyMessage} disabled />
        )}
      </nldd-menu>
    </nldd-combo-box>
  );

  // Without a label there is no field to wrap it in; the combo box carries its
  // own accessible name in that case.
  if (!label) return comboBox;

  return (
    <nldd-form-field label={label} {...(required ? {} : { optional: true })}>
      {comboBox}
      {message ? (
        // A reason only the server can establish gets no rule of its own; it is
        // named in `unmet` on the input and spelled out here.
        <nldd-validation-list>
          <nldd-validation-item id={MESSAGE_ID}>{message}</nldd-validation-item>
        </nldd-validation-list>
      ) : (
        createLabel && <nldd-form-field-help-text text={createLabel} />
      )}
    </nldd-form-field>
  );
}
