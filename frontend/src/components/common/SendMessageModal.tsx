import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { useSendMessage } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import type { Person } from '@/types';

interface SendMessageModalProps {
  open: boolean;
  onClose: () => void;
  recipient: Person;
}

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

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg mx-4 bg-surface rounded-2xl shadow-xl border border-border animate-in fade-in zoom-in-95 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <h2 className="text-lg font-semibold text-text">{title}</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-secondary hover:bg-gray-100 hover:text-text transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body — textarea fills the space */}
        <div className="px-6 py-4 flex-1">
          <textarea
            className="w-full h-48 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
            placeholder={isAgent ? 'Typ je prompt...' : 'Typ je bericht...'}
            value={text}
            onChange={(e) => setText(e.target.value)}
            autoFocus
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border shrink-0">
          <span className="text-xs text-text-secondary">
            {currentPerson ? `Van: ${currentPerson.naam}` : 'Selecteer eerst een persoon'}
          </span>
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={onClose}>
              Annuleren
            </Button>
            <Button
              variant="primary"
              onClick={handleSend}
              disabled={!text.trim() || sendMessage.isPending || !currentPerson}
            >
              {sendMessage.isPending ? 'Versturen...' : 'Versturen'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
