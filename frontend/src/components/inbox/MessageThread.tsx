import { useState, useEffect, useRef } from 'react';
import { Icon } from '@/components/nldd/Icon';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { useNotification, useReplies, useReplyToNotification, useMarkNotificationRead, useReactToMessage } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { timeAgo } from '@/utils/dates';
import { EmojiPicker } from './EmojiPicker';
import { ReactionBar } from './ReactionBar';
import type { Notification, ReactionSummary } from '@/types';

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

  // The chat bubble itself (asymmetric corner, sender-colored background, a
  // rich-text-content color override so links/buttons read on a dark fill)
  // is not one of the nine design-system patterns — there is no bubble/chat
  // component in nldd — so it stays custom markup. What IS layout (alignment
  // of the bubble to a side, the row it sits in with its hover-revealed
  // react-button) converts to nldd-container below.
  return (
    <nldd-container layout="row" horizontal-alignment={isCurrentUser ? 'right' : 'left'}>
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
              <nldd-text size="xs" weight="medium" style={{ opacity: 0.7, display: 'block', marginBottom: '4px' }}>
                {message.sender_name}
              </nldd-text>
            )}
            {/* This selector override (forcing rich-text content, links and
                buttons to white) has no design-system equivalent: RichTextDisplay
                renders arbitrary user content, and there is no "invert my
                descendants' color" attribute on any nldd-* component. It only
                applies on the filled (isCurrentUser) bubble. */}
            <div className={`text-sm ${isCurrentUser ? '[&_*]:text-white [&_button]:bg-white/20 [&_button]:text-white [&_a]:text-white [&_a]:underline [&_a]:decoration-white/60 [&_a:hover]:!text-white [&_a:hover]:decoration-white' : ''}`}>
              <RichTextDisplay content={message.message} fallback="" />
            </div>
            <nldd-text size="xxs" style={{ display: 'block', marginTop: '4px', opacity: isCurrentUser ? 0.6 : 1 }} {...(isCurrentUser ? { color: 'inherit' } : { color: 'secondary' })}>
              {timeAgo(message.created_at)}
            </nldd-text>
          </div>
          {/* EmojiPicker anchors itself via getBoundingClientRect on a real DOM
              button ref, so this trigger stays a native <button>, matching the
              documented exception in EmojiPicker.tsx/ReactionBar.tsx. */}
          <div className={`shrink-0 pt-1 ${hovered || showPicker ? 'visible' : 'invisible'}`}>
            <button
              ref={smileRef}
              onClick={() => setShowPicker(!showPicker)}
              className="p-1 rounded-full bg-surface border border-border shadow-sm text-text-secondary hover:text-text hover:bg-gray-50 transition-colors"
            >
              <Icon name="face-smiling" size="sm" />
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
        <nldd-container layout="row" horizontal-alignment={isCurrentUser ? 'right' : 'left'}>
          <ReactionBar reactions={reactions} onReact={onReact} />
        </nldd-container>
      </div>
    </nldd-container>
  );
}

export function MessageThread({ notificationId, onClose }: MessageThreadProps) {
  const [replyText, setReplyText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { currentPerson } = useCurrentPerson();
  const { data: parentMessage } = useNotification(notificationId);
  const { data: replies } = useReplies(notificationId);
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

  // Escape is the dialog's own business now. This used to be a keydown listener
  // on document, which the native <dialog> inside nldd-window makes both
  // redundant and wrong: the window closes on the dialog's `cancel` event, so
  // both would fire, and a listener on document also sees the key when the
  // mention popup has already handled it. The `!e.defaultPrevented` guard in
  // the old version was there for exactly that popup, and it only worked as
  // long as nothing else closed the modal too.

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
    <Modal
      open
      onClose={onClose}
      title={parentMessage.title}
      size="lg"
      entityLabel={
        replies ? `${replies.length} ${replies.length === 1 ? 'reactie' : 'reacties'}` : 'Laden...'
      }
      footer={
        <nldd-container layout="row" gap="8" width="full" vertical-alignment="top">
          <nldd-container width="full">
            <RichTextEditor
              value={replyText}
              onChange={setReplyText}
              placeholder="Typ een reactie..."
              rows={2}
              autoFocus
            />
          </nldd-container>
          <Button
            size="sm"
            onClick={handleSendReply}
            disabled={!replyText.trim() || replyMutation.isPending || !currentPerson}
            loading={replyMutation.isPending}
            icon="paper-plane"
          >
            Verstuur
          </Button>
        </nldd-container>
      }
    >
      <nldd-container gap="12">
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
      </nldd-container>
    </Modal>
  );
}
