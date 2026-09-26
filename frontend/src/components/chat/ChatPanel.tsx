import { useEffect } from 'react';
import { useUIStore } from '@/store/ui';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';

/**
 * Fills the split view's inspector pane. Sizing and resizing (the drag handle,
 * the width clamp) belong to the split view, not to this component; see
 * AppLayout for the pane.
 */
export function ChatPanel() {
  const { chatOpen, setChatOpen } = useUIStore();

  // Close on Escape
  useEffect(() => {
    if (!chatOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setChatOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [chatOpen, setChatOpen]);

  return (
    // nldd-container has no height attribute; the panel must fill its pane.
    <nldd-container gap="0" style={{ height: '100%' }}>
      <ChatHeader />
      <ChatMessageList />
      <ChatInput />
    </nldd-container>
  );
}
