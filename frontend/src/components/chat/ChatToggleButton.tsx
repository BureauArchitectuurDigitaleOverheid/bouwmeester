import { useUIStore } from '@/store/ui';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';

export function ChatToggleButton() {
  const { chatOpen, toggleChat } = useUIStore();

  if (chatOpen) return null;

  return (
    // Viewport-fixed floating action button: no nldd-container equivalent for
    // fixed/absolute positioning pinned to a screen corner with a z-index, so
    // this stays plain CSS.
    <div
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: 40,
        borderRadius: '9999px',
        boxShadow: 'var(--semantics-overlays-box-shadow)',
      }}
    >
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
