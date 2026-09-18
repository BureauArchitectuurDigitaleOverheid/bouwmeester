import { useEffect } from 'react';
import { useUIStore } from '@/store/ui';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';

/**
 * Fills the split view's inspector pane. Sizing and resizing (the drag handle,
 * the width clamp) are the split view's job now — this used to be a
 * fixed-position panel it hand-rolled itself; see AppLayout for the pane.
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
    <div className="flex h-full flex-col">
      <ChatHeader />
      <ChatMessageList />
      <ChatInput />
    </div>
  );
}
