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
  searchable = true,
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

  // The `searchable={false}` branch below renders an nldd-dropdown, which
  // needs its own listener: it stops the slotted select's native `change` and
  // re-emits a CustomEvent from the host, so React's onChange on the select
  // never fired. 21 call sites pass `searchable={false}`, and in all of them
  // picking an option did nothing at all.
  const dropdownRef = useRef<HTMLElement>(null);
  useNlddEvent(dropdownRef, 'change', (event) => {
    const next = eventValue(event);
    if (!next) onClear?.();
    else onChange(next);
  });

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

  /**
   * A plain list, for `searchable={false}`.
   *
   * An earlier pass rendered the combo box here too, reasoning that two call
   * sites which look identical should not behave differently. The visible
   * result argued otherwise: a five-option filter showed its own value as
   * truncated, spell-checked, editable text with a clear button beside it,
   * because a combo box is, in its own words, "a text input with autocomplete".
   * A select is not a quieter combo box; it is a different control, and the
   * nineteen call sites that pass `searchable={false}` are asking for it.
   *
   * nldd-dropdown wraps a native <select>, so the browser owns the keyboard,
   * the form value and the accessibility, including type-to-jump. Nothing is
   * lost against typing-to-filter on a list this short.
   */
  const dropdown = (
    <nldd-dropdown
      ref={dropdownRef}
      {...(disabled || isCreating ? { disabled: true } : {})}
      {...(required ? { required: true } : {})}
      {...(message ? { invalid: true } : {})}
      {...(label ? {} : { 'accessible-label': placeholder })}
    >
      {/* No React onChange here: the dropdown calls stopPropagation() on the
          slotted select's native `change` and re-emits its own CustomEvent, so
          a handler bound to the select never runs. The listener sits on the
          dropdown instead (see the useNlddEvent above). */}
      <select value={value ?? ''} disabled={disabled || isCreating} onChange={() => {}}>
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </nldd-dropdown>
  );

  const control = searchable ? comboBox : dropdown;

  // Without a label there is no field to wrap it in; the control carries its
  // own accessible name in that case.
  if (!label) return control;

  return (
    <nldd-form-field label={label} {...(required ? {} : { optional: true })}>
      {control}
      {message ? (
        // A reason only the server can establish gets no rule of its own; it is
        // named in `unmet` on the input and spelled out here.
        <nldd-validation-list>
          <nldd-validation-item id={MESSAGE_ID}>{message}</nldd-validation-item>
        </nldd-validation-list>
      ) : (
        createLabel && <nldd-form-field-help-text>{createLabel}</nldd-form-field-help-text>
      )}
    </nldd-form-field>
  );
}
