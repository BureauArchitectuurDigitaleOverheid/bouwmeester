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
 * This file used to rebuild the whole thing: a fixed backdrop with its own
 * z-index, a header with its own close button, a footer, and the blur. All of
 * that is nldd-window through Modal, which also brings the focus trap and the
 * Escape handling that this version never had.
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
          <nldd-container width="full">
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
