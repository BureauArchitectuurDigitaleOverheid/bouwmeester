import { useEffect, useRef } from 'react';
import { useChat } from '@/contexts/ChatContext';
import { ChatMessageBubble } from './ChatMessageBubble';

export function ChatMessageList() {
  const { messages, isLoading } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {messages.length === 0 && (
        <nldd-inline-dialog
          text="Welkom bij de Bouwmeester-assistent"
          supporting-text="Stel een vraag over het beleidscorpus, maak nodes of taken aan, of zoek informatie."
        />
      )}

      {messages.map((msg, i) => (
        <ChatMessageBubble key={i} message={msg} />
      ))}

      {isLoading && (
        <div className="flex justify-start">
          <nldd-activity-indicator size="20" text="Aan het denken..." show-text timing="instant" />
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
