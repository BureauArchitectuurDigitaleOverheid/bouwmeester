import {
  forwardRef,
  useCallback,
  useRef,
  type ChangeEvent,
  type SelectHTMLAttributes,
} from 'react';
import { eventValue, useNlddEvent } from '@/components/nldd/events';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
}

/** Id linking the field's `unmet` to the validation item that explains it. */
const ERROR_ID = 'select-error';

/**
 * `nldd-dropdown` behind the previous API.
 *
 * The dropdown is a visual shell around a real `<select>`, which stays slotted
 * as a child. That is deliberate on the design system's part: the browser keeps
 * ownership of the keyboard, the form value and the native picker on mobile, so
 * the ref and the `<select>` props keep working as before.
 *
 * `onChange` is the exception, and it has to be relayed. The dropdown listens
 * on the slotted select and calls `stopPropagation()` on the native `change`
 * before re-dispatching its own `CustomEvent` from the host. React 19
 * delegates from the root container, so the stopped native event never
 * reaches the delegate and the replacement is a CustomEvent React does not map
 * to `onChange`: the handler simply never ran. Measured on the auditlog
 * filter, where picking a value left the list unfiltered.
 *
 * `Input.tsx` documents having fixed the same thing for text fields; this is
 * the select half of it.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      error,
      options,
      placeholder,
      className,
      id,
      required,
      disabled,
      onChange,
      name,
      ...props
    },
    ref,
  ) => {
    const dropdownRef = useRef<HTMLElement>(null);

    // Hand the caller something shaped like the change event it expects, so
    // the existing `e.target.value` call sites keep working untouched.
    const relay = useCallback(
      (event: Event) => {
        if (!onChange) return;
        const next = eventValue(event);
        const target = { value: next, name: name ?? '' } as EventTarget & HTMLSelectElement;
        onChange({
          ...(event as unknown as ChangeEvent<HTMLSelectElement>),
          target,
          currentTarget: target,
        });
      },
      [onChange, name],
    );

    useNlddEvent(dropdownRef, 'change', onChange ? relay : undefined);

    const dropdown = (
      <nldd-dropdown
        ref={dropdownRef}
        className={className}
        {...(disabled ? { disabled: true } : {})}
        {...(error ? { invalid: true, unmet: ERROR_ID } : {})}
      >
        <select ref={ref} id={id} name={name} required={required} disabled={disabled} {...props}>
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </nldd-dropdown>
    );

    if (!label) return dropdown;

    return (
      <nldd-form-field label={label} {...(required ? {} : { optional: true })}>
        {dropdown}
        {error && (
          <nldd-validation-list>
            <nldd-validation-item id={ERROR_ID}>{error}</nldd-validation-item>
          </nldd-validation-list>
        )}
      </nldd-form-field>
    );
  },
);

Select.displayName = 'Select';
