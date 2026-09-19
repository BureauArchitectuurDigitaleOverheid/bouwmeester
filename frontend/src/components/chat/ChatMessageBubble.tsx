import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { Icon } from '@/components/nldd/Icon';
import { ChatActionCard } from './ChatActionCard';
import { ChatPendingActionCard } from './ChatPendingActionCard';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { chatAttachmentPreviewUrl, isImageContentType } from '@/api/chat';
import type { ChatMessage } from '@/api/chat';

interface ChatMessageBubbleProps {
  message: ChatMessage;
}

/**
 * Fix LLM output that uses "N.\n**Title**:" instead of proper markdown headings.
 * Converts patterns like "1.\n**Bestaanszekerheid**:" into "### 1. Bestaanszekerheid"
 */
function fixNumberedBoldHeadings(text: string): string {
  return text.replace(
    /^(\d+)\.\n\*\*(.+?)\*\*:?$/gm,
    (_match, num, title) => `### ${num}. ${title}`,
  );
}

/**
 * Rendered through a portal to `document.body`: this component lives inside
 * the split view's inspector pane, and an overlay left as a light-DOM sibling
 * there gets slotted into the main pane and steals its height instead of
 * covering the viewport.
 */
function ImageLightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return createPortal(
    // Full-viewport dimmed overlay behind a portalled image: no nldd component
    // renders an image lightbox, so this stays plain fixed-position CSS.
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'var(--semantics-overlays-backdrop-color)',
      }}
      onClick={onClose}
    >
      <img
        src={src}
        alt={alt}
        style={{
          maxWidth: '90vw',
          maxHeight: '90vh',
          borderRadius: '8px',
          boxShadow: 'var(--primitives-box-shadows-level-4)',
        }}
        onClick={(e) => e.stopPropagation()}
      />
    </div>,
    document.body,
  );
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user';
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();
  const { openLeadDetail } = useLeadDetail();
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null);

  const handleBmLink = useCallback(
    (type: 'node' | 'task' | 'lead', id: string) => {
      if (type === 'node') {
        openNodeDetail(id);
      } else if (type === 'task') {
        openTaskDetail(id);
      } else if (type === 'lead') {
        openLeadDetail(id);
      }
    },
    [openNodeDetail, openTaskDetail, openLeadDetail],
  );

  const attachments = message.attachments ?? [];

  return (
    <>
      <nldd-container
        layout="row"
        gap="0"
        horizontal-alignment={isUser ? 'right' : 'left'}
      >
        {/* No nldd component renders a chat message bubble, so the rounded
            pill shape and its background stay scoped CSS; the background
            color itself comes from the design system's own color tokens
            rather than a hardcoded or Tailwind palette value. */}
        <div
          style={{
            maxWidth: '85%',
            borderRadius: '8px',
            paddingInline: '12px',
            paddingBlock: '8px',
            fontSize: '14px',
            backgroundColor: isUser
              ? 'var(--primitives-color-lintblauw-600)'
              : 'var(--primitives-color-coolgray-100)',
            color: isUser ? 'var(--primitives-color-coolgray-0)' : undefined,
          }}
        >
          {/* Attachment previews (user messages) */}
          {attachments.length > 0 && (
            <nldd-container layout="wrap" gap="6" padding-bottom="6">
              {attachments.map((att) =>
                isImageContentType(att.content_type) ? (
                  // Thumbnail button opening the lightbox: a fixed-size
                  // cropped preview (object-cover, w-16 h-16) with a hover
                  // dim, none of which nldd-image or nldd-avatar offer for
                  // an arbitrary attachment thumbnail.
                  <button
                    key={att.id}
                    onClick={() =>
                      setLightboxSrc({
                        src: chatAttachmentPreviewUrl(att.id),
                        alt: att.bestandsnaam,
                      })
                    }
                    style={{ display: 'block' }}
                  >
                    <img
                      src={chatAttachmentPreviewUrl(att.id)}
                      alt={att.bestandsnaam}
                      className="object-cover hover-dim"
                      style={{ width: '64px', height: '64px', borderRadius: '4px', cursor: 'pointer' }}
                    />
                  </button>
                ) : (
                  // A file-attachment pill: no nldd-tag/nldd-token fits (those
                  // are for labeled values, not file previews), so the chip's
                  // own background/padding stays scoped CSS around
                  // nldd-container's flex layout.
                  <div
                    key={att.id}
                    style={{
                      borderRadius: '4px',
                      paddingInline: '8px',
                      paddingBlock: '4px',
                      fontSize: '12px',
                      backgroundColor: isUser
                        ? 'color-mix(in oklch, var(--primitives-color-lintblauw-700) 50%, transparent)'
                        : 'var(--primitives-color-coolgray-200)',
                    }}
                  >
                    <nldd-container layout="row" gap="4" vertical-alignment="center">
                      <Icon name="file-text" size="sm" />
                      {/* truncate + fixed max-width: no nldd-text equivalent
                          for single-line ellipsis truncation. */}
                      <span className="truncate" style={{ maxWidth: '100px' }}>{att.bestandsnaam}</span>
                    </nldd-container>
                  </div>
                ),
              )}
            </nldd-container>
          )}

          {isUser ? (
            // whitespace-pre-wrap preserves the user's own line breaks; no
            // nldd-text equivalent for that CSS white-space value.
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : message.content ? (
            // prose-sm is the Tailwind Typography plugin styling the
            // rendered markdown's own headings/lists/etc.; not a spacing or
            // color utility this conversion targets.
            <div className="prose-sm">
              <MarkdownRenderer content={fixNumberedBoldHeadings(message.content)} compact onBmLink={handleBmLink} />
            </div>
          ) : null}

          {/* Completed actions */}
          {message.actions.length > 0 && (
            <nldd-container gap="6" padding-top="8">
              {message.actions.map((action, i) => (
                <ChatActionCard key={action.entity_id ?? `action-${i}`} action={action} />
              ))}
            </nldd-container>
          )}

          {/* Pending actions awaiting confirmation */}
          {message.pending_actions.length > 0 && (
            <nldd-container gap="6" padding-top="8">
              {message.pending_actions.map((pa) => (
                <ChatPendingActionCard key={pa.action_id} pendingAction={pa} />
              ))}
            </nldd-container>
          )}
        </div>
      </nldd-container>

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
