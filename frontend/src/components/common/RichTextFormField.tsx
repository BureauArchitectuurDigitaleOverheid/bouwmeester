import { RichTextEditor } from '@/components/common/RichTextEditor';

interface RichTextFormFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
  /** Marks the field as required; without it the label shows "Optioneel". */
  required?: boolean;
}

const DEFAULT_PLACEHOLDER =
  'Optionele beschrijving... Gebruik @ voor personen, # voor nodes/taken, **vet** voor opmaak';

/**
 * A description field.
 *
 * `nldd-form-field` owns the label, which is why this no longer draws its own:
 * the field associates the two without a for/id pair, and it also sets the
 * editor's accessible name. The previous version wrote a plain `<label>` beside
 * a framed editor, so a description field and a text field on the same form had
 * visibly different borders.
 *
 * The design guidelines mark the optional fields rather than the required ones,
 * which the field does itself through `optional`.
 */
export function RichTextFormField({
  label,
  value,
  onChange,
  rows = 3,
  placeholder = DEFAULT_PLACEHOLDER,
  required,
}: RichTextFormFieldProps) {
  return (
    <nldd-form-field label={label} {...(required ? {} : { optional: true })}>
      <RichTextEditor value={value} onChange={onChange} placeholder={placeholder} rows={rows} />
    </nldd-form-field>
  );
}
