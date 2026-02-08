import { Button } from '@/components/common/Button';

interface FormModalFooterProps {
  onCancel: () => void;
  onSubmit: (e: React.FormEvent) => void;
  submitLabel: string;
  isLoading: boolean;
  disabled?: boolean;
  cancelLabel?: string;
}

export function FormModalFooter({
  onCancel,
  onSubmit,
  submitLabel,
  isLoading,
  disabled = false,
  cancelLabel = 'Annuleren',
}: FormModalFooterProps) {
  return (
    <>
      <Button variant="secondary" onClick={onCancel}>
        {cancelLabel}
      </Button>
      <Button
        onClick={onSubmit}
        loading={isLoading}
        disabled={disabled}
      >
        {submitLabel}
      </Button>
    </>
  );
}
