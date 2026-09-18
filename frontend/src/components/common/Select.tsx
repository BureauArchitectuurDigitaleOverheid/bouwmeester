import { forwardRef, type SelectHTMLAttributes } from 'react';

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
 * the ref and every `<select>` prop keep working as before.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, className, id, required, disabled, ...props }, ref) => {
    const dropdown = (
      <nldd-dropdown
        className={className}
        {...(disabled ? { disabled: true } : {})}
        {...(error ? { invalid: true, unmet: ERROR_ID } : {})}
      >
        <select ref={ref} id={id} required={required} disabled={disabled} {...props}>
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
