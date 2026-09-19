import { useState, useCallback, useRef } from 'react';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { useChat } from '@/contexts/ChatContext';
import { useToast } from '@/contexts/ToastContext';
import { chatAttachmentPreviewUrl, isImageContentType } from '@/api/chat';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import type { ChatMention } from '@/api/chat';

const ACCEPTED_TYPES = 'image/*,.pdf,.doc,.docx,.odt,.txt';

/** Walk TipTap JSON and extract plain text + mention entities. */
function parseTiptapContent(jsonStr: string): {
  text: string;
  mentions: ChatMention[];
} {
  const mentions: ChatMention[] = [];
  const seenIds = new Set<string>();

  try {
    const doc = JSON.parse(jsonStr);
    const textParts: string[] = [];

    function walk(node: Record<string, unknown>) {
      if (node.type === 'mention' || node.type === 'hashtagMention') {
        const attrs = node.attrs as Record<string, string> | undefined;
        if (attrs?.id && attrs?.label) {
          const prefix = node.type === 'mention' ? '@' : '#';
          textParts.push(`${prefix}${attrs.label}`);
          if (!seenIds.has(attrs.id)) {
            seenIds.add(attrs.id);
            mentions.push({
              id: attrs.id,
              label: attrs.label,
              type: attrs.mentionType ?? (node.type === 'mention' ? 'person' : 'node'),
            });
          }
        }
        return;
      }
      if (node.type === 'text') {
        textParts.push(node.text as string);
        return;
      }
      if (node.type === 'paragraph' && textParts.length > 0) {
        textParts.push('\n');
      }
      if (Array.isArray(node.content)) {
        for (const child of node.content) {
          walk(child as Record<string, unknown>);
        }
      }
    }

    walk(doc);
    return { text: textParts.join('').trim(), mentions };
  } catch {
    // Fallback for plain text
    return { text: jsonStr.trim(), mentions: [] };
  }
}

// Minimal empty TipTap doc
const EMPTY_DOC = JSON.stringify({ type: 'doc', content: [{ type: 'paragraph' }] });

export function ChatInput() {
  const {
    sendMessage,
    isLoading,
    pendingAttachments,
    uploadingCount,
    addAttachment,
    removeAttachment,
  } = useChat();
  const [value, setValue] = useState(EMPTY_DOC);
  const [editorKey, setEditorKey] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { showError } = useToast();

  const handleSend = useCallback(() => {
    const { text, mentions } = parseTiptapContent(value);
    if ((!text && pendingAttachments.length === 0) || isLoading) return;
    sendMessage(text, mentions);
    setValue(EMPTY_DOC);
    setEditorKey((k) => k + 1);
  }, [value, isLoading, sendMessage, pendingAttachments.length]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        const popup = document.querySelector('.tippy-box');
        if (popup) return;
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      for (const file of Array.from(files)) {
        addAttachment(file).catch((err: Error) => {
          showError(err.message || 'Upload mislukt');
        });
      }
    },
    [addAttachment, showError],
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) {
        handleFiles(e.target.files);
        e.target.value = '';
      }
    },
    [handleFiles],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const files: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }
      if (files.length > 0) {
        e.preventDefault();
        e.stopPropagation();
        handleFiles(files);
      }
    },
    [handleFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      if (e.dataTransfer.files?.length) {
        handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles],
  );

  const hasAttachments = pendingAttachments.length > 0 || uploadingCount > 0;

  return (
    // border-t + the drag-over ring: a focus/drag-state ring around the whole
    // input strip has no nldd-container equivalent (container has no border or
    // ring styling at all, only padding/gap/layout), so this outer chrome
    // stays plain CSS.
    <div
      className={`border-t border-border p-3 ${isDragging ? 'ring-2 ring-primary-400 ring-inset' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Attachment preview strip */}
      {hasAttachments && (
        <nldd-container layout="wrap" gap="8" padding-bottom="8">
          {pendingAttachments.map((att) => (
            // An attachment pill: no nldd-tag/nldd-token fits a file preview
            // with a thumbnail and a remove button, so the chip's own
            // background/rounding stays scoped CSS around nldd-container's
            // flex layout.
            <div
              key={att.id}
              style={{ borderRadius: '8px', paddingInline: '8px', paddingBlock: '6px', fontSize: '12px', backgroundColor: 'var(--primitives-color-coolgray-100)' }}
            >
              <nldd-container layout="row" gap="6" vertical-alignment="center">
                {isImageContentType(att.content_type) ? (
                  // Fixed 32px cropped thumbnail: no nldd-image/nldd-avatar
                  // equivalent for an arbitrary attachment preview at this size.
                  <img
                    src={chatAttachmentPreviewUrl(att.id)}
                    alt={att.bestandsnaam}
                    className="object-cover"
                    style={{ width: '32px', height: '32px', borderRadius: '4px' }}
                  />
                ) : (
                  <Icon name="file-text" size="md" />
                )}
                {/* truncate + fixed max-width: no nldd-text single-line
                    ellipsis equivalent. */}
                <span className="truncate" style={{ maxWidth: '120px' }} title={att.bestandsnaam}>
                  {att.bestandsnaam}
                </span>
                <NlddIconButton
                  icon="close"
                  accessibleLabel="Verwijderen"
                  variant="neutral-transparent"
                  size="xs"
                  onClick={() => removeAttachment(att.id)}
                />
              </nldd-container>
            </div>
          ))}
          {uploadingCount > 0 && (
            <div
              style={{ borderRadius: '8px', paddingInline: '8px', paddingBlock: '6px', fontSize: '12px', backgroundColor: 'var(--primitives-color-coolgray-100)' }}
            >
              <nldd-container layout="row" gap="6" vertical-alignment="center">
                <nldd-activity-indicator size="16" />
                <nldd-text size="xs" color="secondary">Uploaden...</nldd-text>
              </nldd-container>
            </div>
          )}
        </nldd-container>
      )}

      <nldd-container
        layout="row"
        gap="8"
        vertical-alignment="bottom"
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        role="group"
      >
        {/* File picker button */}
        <NlddIconButton
          icon="paperclip"
          accessibleLabel="Bestand toevoegen"
          variant="neutral-transparent"
          size="md"
          disabled={isLoading}
          onClick={() => fileInputRef.current?.click()}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          multiple
          className="hidden"
          onChange={handleFileInputChange}
        />

        <nldd-container width="full" min-width="0" gap="0">
          <RichTextEditor
            key={editorKey}
            value={value}
            onChange={setValue}
            placeholder="Stel een vraag... @ personen, # nodes/taken"
            rows={1}
            readOnly={isLoading}
            autoFocus
          />
        </nldd-container>
        <NlddIconButton
          icon="paper-plane"
          accessibleLabel="Versturen"
          variant="primary"
          size="md"
          disabled={isLoading || uploadingCount > 0}
          onClick={handleSend}
        />
      </nldd-container>
    </div>
  );
}
