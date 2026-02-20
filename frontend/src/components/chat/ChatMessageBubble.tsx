import { useCallback, useEffect, useState } from 'react';
import { FileText } from 'lucide-react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { ChatActionCard } from './ChatActionCard';
import { ChatPendingActionCard } from './ChatPendingActionCard';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { chatAttachmentPreviewUrl, isImageContentType } from '@/api/chat';
import type { ChatMessage } from '@/api/chat';

interface ChatMessageBubbleProps {
  message: ChatMessage;
}

function ImageLightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <img
        src={src}
        alt={alt}
        className="max-w-[90vw] max-h-[90vh] rounded-lg shadow-xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user';
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null);

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

  const attachments = message.attachments ?? [];

  return (
    <>
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
        <div
          className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
            isUser
              ? 'bg-primary-600 text-white'
              : 'bg-gray-100 text-text'
          }`}
        >
          {/* Attachment previews (user messages) */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-1.5">
              {attachments.map((att) =>
                isImageContentType(att.content_type) ? (
                  <button
                    key={att.id}
                    onClick={() =>
                      setLightboxSrc({
                        src: chatAttachmentPreviewUrl(att.id),
                        alt: att.bestandsnaam,
                      })
                    }
                    className="block"
                  >
                    <img
                      src={chatAttachmentPreviewUrl(att.id)}
                      alt={att.bestandsnaam}
                      className="w-16 h-16 object-cover rounded cursor-pointer hover:opacity-80 transition-opacity"
                    />
                  </button>
                ) : (
                  <div
                    key={att.id}
                    className={`flex items-center gap-1 rounded px-2 py-1 text-xs ${
                      isUser ? 'bg-primary-700/50' : 'bg-gray-200'
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate max-w-[100px]">{att.bestandsnaam}</span>
                  </div>
                ),
              )}
            </div>
          )}

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
                <ChatActionCard key={action.entity_id ?? `action-${i}`} action={action} />
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

      {/* Image lightbox */}
      {lightboxSrc && (
        <ImageLightbox
          src={lightboxSrc.src}
          alt={lightboxSrc.alt}
          onClose={() => setLightboxSrc(null)}
        />
      )}
    </>
  );
}
