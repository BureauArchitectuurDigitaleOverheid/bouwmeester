import { useEffect } from 'react';
import { useUIStore } from '@/store/ui';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';

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
    <div
      className={`fixed top-0 right-0 h-full w-96 max-w-full z-40 bg-white border-l border-border shadow-xl flex flex-col transition-transform duration-300 ${
        chatOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      <ChatHeader />
      <ChatMessageList />
      <ChatInput />
    </div>
  );
}
