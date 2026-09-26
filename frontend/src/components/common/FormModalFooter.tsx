import { NlddButton } from '@/components/nldd/NlddButton';

interface FormModalFooterProps {
  onCancel: () => void;
  onSubmit: () => void;
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
      <NlddButton variant="secondary" onClick={onCancel} text={cancelLabel} />
      <NlddButton
        onClick={onSubmit}
        loading={isLoading}
        disabled={disabled}
        text={submitLabel}
      />
    </>
  );
}
