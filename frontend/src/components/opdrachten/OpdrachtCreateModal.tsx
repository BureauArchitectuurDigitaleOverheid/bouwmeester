import { Modal } from '@/components/common/Modal';
import { OpdrachtForm } from '@/components/opdrachten/OpdrachtForm';
import { useOpdrachtCreate } from '@/contexts/OpdrachtCreateContext';

export function OpdrachtCreateModal() {
  const { isOpen, defaults, closeOpdrachtCreate } = useOpdrachtCreate();

  return (
    <Modal open={isOpen} onClose={closeOpdrachtCreate} title="Nieuwe opdracht" size="lg" zIndex={45}>
      <OpdrachtForm
        onClose={closeOpdrachtCreate}
        onSuccess={closeOpdrachtCreate}
        defaults={defaults ?? undefined}
      />
    </Modal>
  );
}
