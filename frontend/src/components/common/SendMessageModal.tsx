import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { useSendMessage } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import type { Person } from '@/types';

interface SendMessageModalProps {
  open: boolean;
  onClose: () => void;
  recipient: Person;
}

/**
 * Uses the shared Modal rather than its own overlay.
 *
 * Modal is nldd-window, which brings the backdrop, the header and its close
 * button, the footer, the focus trap and the Escape handling. Rebuilding any of
 * that here would only lose the focus trap.
 */
export function SendMessageModal({ open, onClose, recipient }: SendMessageModalProps) {
  const [text, setText] = useState('');
  const { currentPerson } = useCurrentPerson();
  const sendMessage = useSendMessage();

  const isAgent = recipient.is_agent;
  const title = `${isAgent ? 'Prompt' : 'Bericht'} aan ${recipient.naam}`;

  useEffect(() => {
    if (!open) setText('');
  }, [open]);

  function handleSend() {
    if (!currentPerson || !text.trim()) return;
    sendMessage.mutate(
      {
        person_id: recipient.id,
        sender_id: currentPerson.id,
        message: text.trim(),
      },
      {
        onSuccess: () => {
          setText('');
          onClose();
        },
      },
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="lg"
      footer={
        <nldd-container layout="row" gap="12" vertical-alignment="center" width="full">
          {/* fit-content + row-fill rather than the container default of full:
              that default takes a hard 100% of the row and squeezes the
              buttons beside it below their own labels. */}
          <nldd-container width="fit-content" className="row-fill">
            <nldd-text size="xs" color="secondary">
              {currentPerson ? `Van: ${currentPerson.naam}` : 'Selecteer eerst een persoon'}
            </nldd-text>
          </nldd-container>
          <nldd-container layout="row" gap="12">
            <Button variant="secondary" onClick={onClose}>
              Annuleren
            </Button>
            <Button
              variant="primary"
              onClick={handleSend}
              loading={sendMessage.isPending}
              disabled={!text.trim() || !currentPerson}
            >
              Versturen
            </Button>
          </nldd-container>
        </nldd-container>
      }
    >
      <RichTextEditor
        value={text}
        onChange={setText}
        placeholder={
          isAgent
            ? 'Typ je prompt... Gebruik @ voor personen, # voor nodes'
            : 'Typ je bericht... Gebruik @ voor personen, # voor nodes'
        }
        rows={8}
        autoFocus
      />
    </Modal>
  );
}
