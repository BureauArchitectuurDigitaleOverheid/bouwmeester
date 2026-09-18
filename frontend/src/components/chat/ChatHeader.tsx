import { useChat } from '@/contexts/ChatContext';
import { useUIStore } from '@/store/ui';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';

export function ChatHeader() {
  const { clearConversation } = useChat();
  const setChatOpen = useUIStore((s) => s.setChatOpen);

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border">
      <h2 className="text-sm font-semibold text-text">Assistent</h2>
      <div className="flex items-center gap-1">
        <NlddIconButton
          icon="trash"
          accessibleLabel="Gesprek wissen"
          variant="neutral-transparent"
          size="sm"
          onClick={clearConversation}
        />
        <NlddIconButton
          icon="close"
          accessibleLabel="Sluiten"
          variant="neutral-transparent"
          size="sm"
          onClick={() => setChatOpen(false)}
        />
      </div>
    </div>
  );
}
