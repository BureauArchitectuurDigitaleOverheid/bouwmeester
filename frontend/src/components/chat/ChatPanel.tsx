import { useCallback, useEffect, useRef } from 'react';
import { useUIStore } from '@/store/ui';
import { ChatHeader } from './ChatHeader';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';

export function ChatPanel() {
  const { chatOpen, setChatOpen, chatWidth, setChatWidth } = useUIStore();
  const isDragging = useRef(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    if (!chatOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setChatOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [chatOpen, setChatOpen]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      isDragging.current = true;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      const handleMouseMove = (ev: MouseEvent) => {
        if (!isDragging.current) return;
        const newWidth = window.innerWidth - ev.clientX;
        setChatWidth(newWidth);
      };

      const handleMouseUp = () => {
        isDragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [setChatWidth],
  );

  return (
    <div
      ref={panelRef}
      style={{ width: chatWidth }}
      className={`fixed top-0 right-0 h-full max-w-full z-40 bg-white border-l border-border shadow-xl flex flex-col transition-transform duration-300 ${
        chatOpen ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      {/* Drag handle */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-primary-300 active:bg-primary-400 transition-colors z-10"
        onMouseDown={handleMouseDown}
      />
      <ChatHeader />
      <ChatMessageList />
      <ChatInput />
    </div>
  );
}
