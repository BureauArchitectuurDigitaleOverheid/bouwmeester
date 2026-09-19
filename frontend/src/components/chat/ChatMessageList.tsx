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
    // flex-1 + overflow-y-auto: this pane must grow to fill the space ChatPanel
    // gives it and scroll independently, which nldd-container's height="auto"
    // block layout can't express — no nldd primitive for a flex-growing
    // scroll region, so the outer sizing stays plain CSS.
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <nldd-container gap="12" padding="16">
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
          <nldd-activity-indicator size="20" text="Aan het denken..." show-text timing="instant" />
        )}
      </nldd-container>

      <div ref={bottomRef} />
    </div>
  );
}
