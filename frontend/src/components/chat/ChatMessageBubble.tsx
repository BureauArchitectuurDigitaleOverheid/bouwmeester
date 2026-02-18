import { useCallback } from 'react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { ChatActionCard } from './ChatActionCard';
import { ChatPendingActionCard } from './ChatPendingActionCard';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import type { ChatMessage } from '@/api/chat';

interface ChatMessageBubbleProps {
  message: ChatMessage;
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user';
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();

  const handleBmLink = useCallback(
    (type: 'node' | 'task', id: string) => {
      if (type === 'node') {
        openNodeDetail(id);
      } else if (type === 'task') {
        openTaskDetail(id);
      }
    },
    [openNodeDetail, openTaskDetail],
  );

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'bg-primary-600 text-white'
            : 'bg-gray-100 text-text'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : message.content ? (
          <div className="prose-sm">
            <MarkdownRenderer content={message.content} onBmLink={handleBmLink} />
          </div>
        ) : null}

        {/* Completed actions */}
        {message.actions.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {message.actions.map((action, i) => (
              <ChatActionCard key={i} action={action} />
            ))}
          </div>
        )}

        {/* Pending actions awaiting confirmation */}
        {message.pending_actions.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {message.pending_actions.map((pa) => (
              <ChatPendingActionCard key={pa.action_id} pendingAction={pa} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
