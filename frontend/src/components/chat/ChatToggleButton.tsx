import { useUIStore } from '@/store/ui';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';

export function ChatToggleButton() {
  const { chatOpen, toggleChat } = useUIStore();

  if (chatOpen) return null;

  return (
    // Viewport-fixed floating action button: no nldd-container equivalent for
    // fixed/absolute positioning pinned to a screen corner with a z-index, so
    // this stays plain CSS.
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
