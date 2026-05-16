import { useState } from 'react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { useCreateNode } from '@/hooks/useNodes';
import { INSTRUMENT_TYPE_LABELS, NodeType } from '@/types';

interface NieuwInstrumentDialogProps {
  open: boolean;
  /** Prefilled title — the text the user typed in the instrument dropdown. */
  initialTitle: string;
  onClose: () => void;
  /** Called with the new instrument's id after a successful create. */
  onCreated: (id: string) => void;
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
      onCreated(node.id);
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
      zIndex={60}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            type="submit"
            form="nieuw-instrument-form"
            loading={createNode.isPending}
          >
            Aanmaken
          </Button>
        </>
      }
    >
      <form id="nieuw-instrument-form" onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-text mb-1">Titel *</label>
          <input
            type="text"
            value={titel}
            onChange={e => setTitel(e.target.value)}
            required
            autoFocus
            className="w-full px-3 py-2 text-sm rounded-lg border border-border"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-text mb-1">Type *</label>
          <select
            value={type}
            onChange={e => setType(e.target.value)}
            required
            className="w-full px-3 py-2 text-sm rounded-lg border border-border"
          >
            <option value="">Kies type...</option>
            {Object.entries(INSTRUMENT_TYPE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>
        {error && (
          <div className="p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}
