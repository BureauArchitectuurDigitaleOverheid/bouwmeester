import { RichTextEditor } from '@/components/common/RichTextEditor';

interface RichTextFormFieldProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
}

const DEFAULT_PLACEHOLDER = 'Optionele beschrijving... Gebruik @ voor personen, # voor nodes/taken, **vet** voor opmaak';

export function RichTextFormField({
  label,
  value,
  onChange,
  rows = 3,
  placeholder = DEFAULT_PLACEHOLDER,
}: RichTextFormFieldProps) {
  return (
    <div className="space-y-1.5">
      {label && <label className="block text-sm font-medium text-text">{label}</label>}
      <RichTextEditor
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        rows={rows}
      />
    </div>
  );
}
