import { useState, useCallback } from 'react';
import { Send } from 'lucide-react';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { useChat } from '@/contexts/ChatContext';
import type { ChatMention } from '@/api/chat';

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
  const { sendMessage, isLoading } = useChat();
  const [value, setValue] = useState(EMPTY_DOC);
  const [editorKey, setEditorKey] = useState(0);

  const handleSend = useCallback(() => {
    const { text, mentions } = parseTiptapContent(value);
    if (!text || isLoading) return;
    sendMessage(text, mentions);
    setValue(EMPTY_DOC);
    setEditorKey((k) => k + 1);
  }, [value, isLoading, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        // Only intercept if the suggestion popup is NOT open.
        // TipTap's mention suggestion handles Enter itself when open,
        // so we check if there's a tippy popup visible.
        const popup = document.querySelector('.tippy-box');
        if (popup) return;

        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div className="border-t border-border p-3 bg-white">
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <div className="flex items-end gap-2" onKeyDown={handleKeyDown}>
        <div className="flex-1 min-w-0 chat-editor">
          <RichTextEditor
            key={editorKey}
            value={value}
            onChange={setValue}
            placeholder="Stel een vraag... @ personen, # nodes/taken"
            rows={1}
            readOnly={isLoading}
            autoFocus
          />
        </div>
        <button
          onClick={handleSend}
          disabled={isLoading}
          className="p-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
          title="Versturen"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
      <style>{`
        .chat-editor .rich-text-editor {
          border-radius: 0.5rem;
        }
        .chat-editor .rich-text-editor .ProseMirror {
          min-height: 1.5rem !important;
          max-height: 7.5rem;
          overflow-y: auto;
        }
        .chat-editor .EditorContent,
        .chat-editor [class*="prose"] {
          padding: 0.375rem 0.75rem;
        }
      `}</style>
    </div>
  );
}
