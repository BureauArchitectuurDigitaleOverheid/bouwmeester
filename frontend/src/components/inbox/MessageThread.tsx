import { useState, useEffect, useRef } from 'react';
import { X, Send, ArrowLeft, Smile } from 'lucide-react';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { Button } from '@/components/common/Button';
import { useNotification, useReplies, useReplyToNotification, useMarkNotificationRead, useReactToMessage } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { timeAgo } from '@/utils/dates';
import { EmojiPicker } from './EmojiPicker';
import { ReactionBar } from './ReactionBar';
import type { Notification, ReactionSummary } from '@/api/notifications';

interface MessageThreadProps {
  notificationId: string;
  onClose: () => void;
}

interface MessageBubbleProps {
  message: Notification;
  isCurrentUser: boolean;
  reactions: ReactionSummary[];
  onReact: (emoji: string) => void;
}

function MessageBubble({ message, isCurrentUser, reactions, onReact }: MessageBubbleProps) {
  const [showPicker, setShowPicker] = useState(false);
  const [hovered, setHovered] = useState(false);
  const smileRef = useRef<HTMLButtonElement>(null);

  return (
    <div className={`flex ${isCurrentUser ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[80%]">
        <div
          className={`relative flex items-start gap-1 ${isCurrentUser ? 'flex-row-reverse' : 'flex-row'}`}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => { if (!showPicker) setHovered(false); }}
        >
          <div
            className={`rounded-2xl px-4 py-2.5 ${
              isCurrentUser
                ? 'bg-primary-600 text-white rounded-br-md'
                : 'bg-gray-100 text-text rounded-bl-md'
            }`}
          >
            {!isCurrentUser && message.sender_name && (
              <p className="text-xs font-medium mb-1 opacity-70">{message.sender_name}</p>
            )}
            <div className={`text-sm ${isCurrentUser ? '[&_*]:text-white [&_button]:bg-white/20 [&_button]:text-white [&_a]:text-white [&_a]:underline [&_a]:decoration-white/60 [&_a:hover]:!text-white [&_a:hover]:decoration-white' : ''}`}>
              <RichTextDisplay content={message.message} fallback="" />
            </div>
            <p className={`text-[10px] mt-1 ${isCurrentUser ? 'text-white/60' : 'text-text-secondary'}`}>
              {timeAgo(message.created_at)}
            </p>
          </div>
          <div className={`shrink-0 pt-1 ${hovered || showPicker ? 'visible' : 'invisible'}`}>
            <button
              ref={smileRef}
              onClick={() => setShowPicker(!showPicker)}
              className="p-1 rounded-full bg-surface border border-border shadow-sm text-text-secondary hover:text-text hover:bg-gray-50 transition-colors"
            >
              <Smile className="h-4 w-4" />
            </button>
            {showPicker && (
              <EmojiPicker
                anchorRef={smileRef}
                onSelect={(emoji) => { onReact(emoji); setShowPicker(false); setHovered(false); }}
                onClose={() => { setShowPicker(false); setHovered(false); }}
              />
            )}
          </div>
        </div>
        <div className={`${isCurrentUser ? 'flex justify-end' : ''}`}>
          <ReactionBar reactions={reactions} onReact={onReact} />
        </div>
      </div>
    </div>
  );
}

export function MessageThread({ notificationId, onClose }: MessageThreadProps) {
  const [replyText, setReplyText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { currentPerson } = useCurrentPerson();
  const personId = currentPerson?.id;
  const { data: parentMessage } = useNotification(notificationId, personId);
  const { data: replies } = useReplies(notificationId, personId);
  const replyMutation = useReplyToNotification();
  const markRead = useMarkNotificationRead();
  const reactMutation = useReactToMessage();

  const handleReact = (messageId: string, emoji: string) => {
    if (!currentPerson) return;
    reactMutation.mutate({
      notificationId: messageId,
      data: { sender_id: currentPerson.id, emoji },
    });
  };

  // Scroll to bottom when replies change (new messages arrive or on first load)
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [replies]);

  // Close modal on Escape key (guard against mention popup consuming Escape first)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Mark as read when opened — only if current user is the recipient (person_id),
  // not the sender.  After a reply the backend marks the root unread for the
  // recipient; we must not immediately re-mark it read for the sender.
  useEffect(() => {
    if (
      parentMessage &&
      !parentMessage.is_read &&
      currentPerson?.id === parentMessage.person_id
    ) {
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
      <div className="relative w-full max-w-2xl mx-4 bg-surface rounded-2xl shadow-xl border border-border animate-in fade-in zoom-in-95 flex flex-col max-h-[80vh]">
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
            reactions={parentMessage.reactions}
            onReact={(emoji) => handleReact(parentMessage.id, emoji)}
          />

          {/* Replies */}
          {replies?.map((reply) => (
            <MessageBubble
              key={reply.id}
              message={reply}
              isCurrentUser={reply.sender_id === currentPerson?.id}
              reactions={reply.reactions}
              onReact={(emoji) => handleReact(reply.id, emoji)}
            />
          ))}
          <div ref={messagesEndRef} />
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
                autoFocus
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
