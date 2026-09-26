import { useState } from 'react';
import { useChat } from '@/contexts/ChatContext';
import { NlddButton } from '@/components/nldd/NlddButton';
import type { PendingAction } from '@/api/chat';

interface ChatPendingActionCardProps {
  pendingAction: PendingAction;
}

export function ChatPendingActionCard({ pendingAction }: ChatPendingActionCardProps) {
  const { confirmAction } = useChat();
  const [confirming, setConfirming] = useState(false);

  const handleConfirm = async (approved: boolean) => {
    setConfirming(true);
    await confirmAction(pendingAction.action_id, approved);
    setConfirming(false);
  };

  return (
    <nldd-card>
      <nldd-container gap="6" padding="12">
        <nldd-text-cell size="sm" color="warning" text={pendingAction.description} width="full" />
        <nldd-container layout="row" gap="8">
          <NlddButton
            text="Bevestigen"
            variant="primary"
            size="xs"
            loading={confirming}
            disabled={confirming}
            onClick={() => handleConfirm(true)}
          />
          <NlddButton
            text="Annuleren"
            variant="secondary"
            size="xs"
            disabled={confirming}
            onClick={() => handleConfirm(false)}
          />
        </nldd-container>
      </nldd-container>
    </nldd-card>
  );
}
