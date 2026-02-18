import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
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
        <div className="text-center text-text-secondary text-sm py-8">
          <p className="font-medium mb-1">Welkom bij de Bouwmeester-assistent</p>
          <p>Stel een vraag over het beleidscorpus, maak nodes of taken aan, of zoek informatie.</p>
        </div>
      )}

      {messages.map((msg, i) => (
        <ChatMessageBubble key={i} message={msg} />
      ))}

      {isLoading && (
        <div className="flex justify-start">
          <div className="bg-gray-100 rounded-lg px-3 py-2 flex items-center gap-2 text-sm text-text-secondary">
            <Loader2 className="w-4 h-4 animate-spin" />
            Aan het denken...
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
