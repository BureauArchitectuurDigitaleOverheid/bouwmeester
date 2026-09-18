import { forwardRef, type InputHTMLAttributes } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

/** Id linking the input's `unmet` to the validation item that explains it. */
const ERROR_ID = 'input-error';

/** The types nldd-text-field itself accepts; everything else needs its own element. */
const TEXT_TYPES = new Set(['text', 'email', 'tel', 'url']);

/**
 * `nldd-form-field` plus the input element that matches the requested type.
 *
 * The design system splits by type where the browser does: `nldd-text-field`
 * covers text/email/tel/url, `nldd-number-field` a number with its steppers, and
 * `nldd-date-field` a date. Routing here keeps every existing `<Input type=...>`
 * call site working while each one gets the right keyboard and controls.
 *
 * Two behaviours change for the better: the field associates its own label (the
 * old `id || label.toLowerCase()` fallback could collide between two fields with
 * the same label), and it marks what is OPTIONAL instead of starring what is
 * required, per the design system's convention.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, className, id, type = 'text', required, disabled, ...props }, ref) => {
    // Shared across all three elements. `value` is deliberately left out: the
    // number field takes a number where the others take a string.
    const shared = {
      ref: ref as React.Ref<HTMLElement>,
      className,
      ...(id ? { 'input-id': id } : {}),
      ...(required ? { required: true as const } : {}),
      ...(disabled ? { disabled: true as const } : {}),
      ...(error ? { invalid: true as const, unmet: ERROR_ID } : {}),
      ...(label ? {} : { 'accessible-label': props.placeholder ?? '' }),
      ...(props.placeholder ? { placeholder: props.placeholder } : {}),
      ...(props.name ? { name: props.name } : {}),
    };

    const stringValue = props.value !== undefined ? String(props.value) : undefined;

    let field;
    if (type === 'number') {
      const numeric = stringValue === undefined || stringValue === '' ? undefined : Number(stringValue);
      field = (
        <nldd-number-field
          {...shared}
          {...(numeric !== undefined && !Number.isNaN(numeric) ? { value: numeric } : {})}
        />
      );
    } else if (type === 'date') {
      field = <nldd-date-field {...shared} {...(stringValue ? { value: stringValue } : {})} />;
    } else {
      // Only the four types the element supports reach its `type`; anything else
      // (password, search, ...) falls back to a plain text field rather than
      // landing an attribute the element does not understand.
      const textType = TEXT_TYPES.has(type) && type !== 'text' ? (type as 'email' | 'tel' | 'url') : undefined;
      field = (
        <nldd-text-field
          {...shared}
          {...(stringValue !== undefined ? { value: stringValue } : {})}
          {...(textType ? { type: textType } : {})}
        />
      );
    }

    if (!label) return field;

    return (
      <nldd-form-field label={label} {...(required ? {} : { optional: true })}>
        {field}
        {error ? (
          <nldd-validation-list>
            <nldd-validation-item id={ERROR_ID}>{error}</nldd-validation-item>
          </nldd-validation-list>
        ) : (
          helperText && <nldd-form-field-help-text text={helperText} />
        )}
      </nldd-form-field>
    );
  },
);

Input.displayName = 'Input';
