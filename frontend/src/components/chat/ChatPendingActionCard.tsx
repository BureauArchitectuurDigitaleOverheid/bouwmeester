import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useChat } from '@/contexts/ChatContext';
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
    <div className="p-2 rounded-md bg-amber-50 border border-amber-200 text-xs">
      <p className="font-medium text-amber-800 mb-1.5">{pendingAction.description}</p>
      <div className="flex gap-2">
        <button
          onClick={() => handleConfirm(true)}
          disabled={confirming}
          className="px-2 py-1 rounded bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors text-xs font-medium"
        >
          {confirming ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Bevestigen'}
        </button>
        <button
          onClick={() => handleConfirm(false)}
          disabled={confirming}
          className="px-2 py-1 rounded border border-border text-text-secondary hover:bg-gray-100 disabled:opacity-50 transition-colors text-xs"
        >
          Annuleren
        </button>
      </div>
    </div>
  );
}
