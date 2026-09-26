import { useState } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Select } from '@/components/common/Select';
import { useCreateNode } from '@/hooks/useNodes';
import { INSTRUMENT_TYPE_LABELS, NodeType, type CorpusNode } from '@/types';
import { NlddButton } from '@/components/nldd/NlddButton';

interface NieuwInstrumentDialogProps {
  open: boolean;
  /** Prefilled title — the text the user typed in the instrument dropdown. */
  initialTitle: string;
  onClose: () => void;
  /** Called with the freshly created instrument node after a successful create. */
  onCreated: (node: CorpusNode) => void;
}

export function NieuwInstrumentDialog({ open, initialTitle, onClose, onCreated }: NieuwInstrumentDialogProps) {
  const createNode = useCreateNode();
  const [titel, setTitel] = useState(initialTitle);
  const [type, setType] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!titel.trim()) {
      setError('Geef een titel op.');
      return;
    }
    if (!type) {
      setError('Kies een type.');
      return;
    }
    setError(null);
    try {
      const node = await createNode.mutateAsync({
        title: titel.trim(),
        node_type: NodeType.INSTRUMENT,
        instrument_type: type,
      });
      onCreated(node);
    } catch {
      setError('Fout bij aanmaken van instrument.');
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Nieuw instrument"
      size="sm"
      footer={
        <>
          <NlddButton variant="secondary" type="button" onClick={onClose} text="Annuleren" />
          <NlddButton
            type="submit"
            form="nieuw-instrument-form"
            loading={createNode.isPending}
            text="Aanmaken"
          />
        </>
      }
    >
      {/* A real <form> element is required for the submit button's
          form="nieuw-instrument-form" association; nldd-form has no bearing
          on that, so the element itself stays plain and only its layout
          moves to nldd-container. */}
      <form id="nieuw-instrument-form" onSubmit={handleSubmit}>
        <nldd-container gap="16">
          <Input
            label="Titel"
            value={titel}
            onChange={e => setTitel(e.target.value)}
            required
            autoFocus
          />
          <Select
            label="Type"
            value={type}
            onChange={e => setType(e.target.value)}
            placeholder="Kies type..."
            required
            options={Object.entries(INSTRUMENT_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
          />
          {error && <nldd-banner variant="critical" size="sm" text={error} />}
        </nldd-container>
      </form>
    </Modal>
  );
}
