import { useState, useEffect } from 'react';
import { X, Send, ArrowLeft } from 'lucide-react';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { Button } from '@/components/common/Button';
import { useNotification, useReplies, useReplyToNotification, useMarkNotificationRead } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import type { Notification } from '@/api/notifications';

interface MessageThreadProps {
  notificationId: string;
  onClose: () => void;
}

function timeAgo(dateStr: string): string {
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now.getTime() - then.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'Zojuist';
  if (diffMin < 60) return `${diffMin}m geleden`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}u geleden`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays}d geleden`;
}

function MessageBubble({ message, isCurrentUser }: { message: Notification; isCurrentUser: boolean }) {
  return (
    <div className={`flex ${isCurrentUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
          isCurrentUser
            ? 'bg-primary-600 text-white rounded-br-md'
            : 'bg-gray-100 text-text rounded-bl-md'
        }`}
      >
        {!isCurrentUser && message.sender_name && (
          <p className="text-xs font-medium mb-1 opacity-70">{message.sender_name}</p>
        )}
        <div className={`text-sm ${isCurrentUser ? '[&_*]:text-white' : ''}`}>
          <RichTextDisplay content={message.message} fallback="" />
        </div>
        <p className={`text-[10px] mt-1 ${isCurrentUser ? 'text-white/60' : 'text-text-secondary'}`}>
          {timeAgo(message.created_at)}
        </p>
      </div>
    </div>
  );
}

export function MessageThread({ notificationId, onClose }: MessageThreadProps) {
  const [replyText, setReplyText] = useState('');
  const { currentPerson } = useCurrentPerson();
  const { data: parentMessage } = useNotification(notificationId);
  const { data: replies } = useReplies(notificationId);
  const replyMutation = useReplyToNotification();
  const markRead = useMarkNotificationRead();

  // Mark as read when opened
  useEffect(() => {
    if (parentMessage && !parentMessage.is_read) {
      markRead.mutate(parentMessage.id);
    }
  }, [parentMessage?.id, parentMessage?.is_read]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSendReply = () => {
    if (!currentPerson || !replyText.trim()) return;
    replyMutation.mutate(
      {
        notificationId,
        data: {
          sender_id: currentPerson.id,
          message: replyText.trim(),
        },
      },
      {
        onSuccess: () => setReplyText(''),
      },
    );
  };

  if (!parentMessage) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg mx-4 bg-surface rounded-2xl shadow-xl border border-border animate-in fade-in zoom-in-95 flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border shrink-0">
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-secondary hover:bg-gray-100 hover:text-text transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-text truncate">{parentMessage.title}</h3>
            <p className="text-xs text-text-secondary">
              {replies ? `${replies.length} ${replies.length === 1 ? 'reactie' : 'reacties'}` : 'Laden...'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-secondary hover:bg-gray-100 hover:text-text transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {/* Original message */}
          <MessageBubble
            message={parentMessage}
            isCurrentUser={parentMessage.sender_id === currentPerson?.id}
          />

          {/* Replies */}
          {replies?.map((reply) => (
            <MessageBubble
              key={reply.id}
              message={reply}
              isCurrentUser={reply.sender_id === currentPerson?.id}
            />
          ))}
        </div>

        {/* Reply input */}
        <div className="border-t border-border px-4 py-3 shrink-0">
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <RichTextEditor
                value={replyText}
                onChange={setReplyText}
                placeholder="Typ een reactie..."
                rows={2}
              />
            </div>
            <Button
              size="sm"
              onClick={handleSendReply}
              disabled={!replyText.trim() || replyMutation.isPending || !currentPerson}
              loading={replyMutation.isPending}
              icon={<Send className="h-3.5 w-3.5" />}
            >
              Verstuur
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
