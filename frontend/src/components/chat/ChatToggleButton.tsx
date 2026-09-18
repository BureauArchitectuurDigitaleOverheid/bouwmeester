import { useUIStore } from '@/store/ui';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';

export function ChatToggleButton() {
  const { chatOpen, toggleChat } = useUIStore();

  if (chatOpen) return null;

  return (
    <div className="fixed bottom-6 right-6 z-40 rounded-full shadow-lg">
      <NlddIconButton
        icon="message-rectangle-text"
        accessibleLabel="AI Assistent"
        variant="accent-filled"
        size="lg"
        onClick={toggleChat}
      />
    </div>
  );
}
