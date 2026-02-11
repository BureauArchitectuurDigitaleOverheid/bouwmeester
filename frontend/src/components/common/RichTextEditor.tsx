import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import { useEditor, EditorContent, type Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Mention from '@tiptap/extension-mention';
import Placeholder from '@tiptap/extension-placeholder';
import { apiGet } from '@/api/client';
import { formatFunctie } from '@/types';
import type { Person, OrganisatieEenheid } from '@/types';
import type { MentionSearchResult } from '@/api/mentions';
import type { SuggestionProps, SuggestionKeyDownProps } from '@tiptap/suggestion';
import { ReactRenderer } from '@tiptap/react';

// ─── Types ──────────────────────────────────────────────────────────────────

interface RichTextEditorProps {
  value: string;
  onChange: (json: string) => void;
  placeholder?: string;
  rows?: number;
  readOnly?: boolean;
  id?: string;
  autoFocus?: boolean;
}

interface SuggestionItem {
  id: string;
  label: string;
  subtitle?: string;
  mentionType?: string;
}

interface SuggestionListProps {
  items: SuggestionItem[];
  command: (item: SuggestionItem) => void;
}

// ─── Mention type styling ────────────────────────────────────────────────────

const MENTION_TYPE_LABELS: Record<string, string> = {
  person: 'Persoon',
  organisatie: 'Afdeling',
  node: 'Node',
  task: 'Taak',
  tag: 'Tag',
};

const MENTION_TYPE_STYLES: Record<string, string> = {
  person: 'bg-blue-50 text-blue-700',
  organisatie: 'bg-emerald-50 text-emerald-700',
  node: 'bg-blue-50 text-blue-700',
  task: 'bg-amber-50 text-amber-700',
  tag: 'bg-slate-100 text-slate-600',
};

// ─── Suggestion List Component ──────────────────────────────────────────────

const SuggestionList = forwardRef<{ onKeyDown: (props: SuggestionKeyDownProps) => boolean }, SuggestionListProps>(
  ({ items, command }, ref) => {
    const [selectedIndex, setSelectedIndex] = useState(0);

    useEffect(() => {
      setSelectedIndex(0);
    }, [items]);

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }: SuggestionKeyDownProps) => {
        if (event.key === 'ArrowUp') {
          setSelectedIndex((i) => (i + items.length - 1) % items.length);
          return true;
        }
        if (event.key === 'ArrowDown') {
          setSelectedIndex((i) => (i + 1) % items.length);
          return true;
        }
        if (event.key === 'Enter') {
          if (items[selectedIndex]) {
            command(items[selectedIndex]);
          }
          return true;
        }
        if (event.key === 'Escape') {
          return true;
        }
        return false;
      },
    }));

    if (!items.length || (items.length === 1 && items[0].id === '__hint__')) {
      return (
        <div className="rounded-xl border border-border bg-white shadow-lg py-2 px-3">
          <p className="text-xs text-text-secondary">
            {items[0]?.id === '__hint__' ? 'Typ om te zoeken...' : 'Geen resultaten'}
          </p>
        </div>
      );
    }

    return (
      <div className="rounded-xl border border-border bg-white shadow-lg py-1 max-h-48 overflow-y-auto min-w-[240px]">
        {items.map((item, index) => (
          <button
            key={item.id}
            onClick={() => command(item)}
            onMouseEnter={() => setSelectedIndex(index)}
            className={`flex items-start gap-2 w-full px-3 py-1.5 text-left transition-colors ${
              index === selectedIndex ? 'bg-primary-50 text-primary-700' : 'text-text hover:bg-gray-50'
            }`}
          >
            {item.mentionType && (
              <span className={`shrink-0 mt-0.5 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-none ${
                MENTION_TYPE_STYLES[item.mentionType] ?? 'bg-gray-100 text-gray-600'
              }`}>
                {MENTION_TYPE_LABELS[item.mentionType] ?? item.mentionType}
              </span>
            )}
            <div className="flex flex-col min-w-0">
              <span className="text-sm font-medium truncate">{item.label}</span>
              {item.subtitle && (
                <span className="text-xs text-text-secondary truncate">{item.subtitle}</span>
              )}
            </div>
          </button>
        ))}
      </div>
    );
  },
);
SuggestionList.displayName = 'SuggestionList';

// ─── Suggestion utilities ───────────────────────────────────────────────────

function createSuggestionConfig(
  fetchItems: (query: string) => Promise<SuggestionItem[]>,
) {
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  return {
    items: async ({ query }: { query: string }) => {
      if (debounceTimer) clearTimeout(debounceTimer);
      return new Promise<SuggestionItem[]>((resolve) => {
        debounceTimer = setTimeout(async () => {
          const results = await fetchItems(query);
          resolve(results);
        }, 150);
      });
    },

    render: () => {
      let component: ReactRenderer<{ onKeyDown: (props: SuggestionKeyDownProps) => boolean }> | null = null;
      let popup: HTMLDivElement | null = null;

      return {
        onStart: (props: SuggestionProps) => {
          component = new ReactRenderer(SuggestionList, {
            props: { items: props.items, command: props.command },
            editor: props.editor,
          });

          popup = document.createElement('div');
          popup.style.position = 'absolute';
          popup.style.zIndex = '50';
          popup.appendChild(component.element);
          document.body.appendChild(popup);

          if (props.clientRect) {
            const rect = props.clientRect();
            if (rect) {
              popup.style.left = `${rect.left + window.scrollX}px`;
              popup.style.top = `${rect.bottom + window.scrollY + 4}px`;
            }
          }
        },

        onUpdate: (props: SuggestionProps) => {
          component?.updateProps({ items: props.items, command: props.command });

          if (popup && props.clientRect) {
            const rect = props.clientRect();
            if (rect) {
              popup.style.left = `${rect.left + window.scrollX}px`;
              popup.style.top = `${rect.bottom + window.scrollY + 4}px`;
            }
          }
        },

        onKeyDown: (props: SuggestionKeyDownProps) => {
          if (props.event.key === 'Escape') {
            popup?.remove();
            component?.destroy();
            popup = null;
            component = null;
            return true;
          }
          return component?.ref?.onKeyDown(props) ?? false;
        },

        onExit: () => {
          popup?.remove();
          component?.destroy();
          popup = null;
          component = null;
        },
      };
    },
  };
}

// ─── Fetch helpers ──────────────────────────────────────────────────────────

async function fetchPeopleAndOrgs(query: string): Promise<SuggestionItem[]> {
  try {
    const [people, orgs] = await Promise.all([
      apiGet<Person[]>('/api/people/search', { q: query, limit: 8 }),
      apiGet<OrganisatieEenheid[]>('/api/organisatie/search', { q: query, limit: 5 }),
    ]);
    const personItems: SuggestionItem[] = people.map((p) => ({
      id: p.id,
      label: p.naam,
      subtitle: formatFunctie(p.functie),
      mentionType: 'person',
    }));
    const orgItems: SuggestionItem[] = orgs.map((o) => ({
      id: o.id,
      label: o.naam,
      subtitle: o.type.replace(/_/g, ' '),
      mentionType: 'organisatie',
    }));
    return [...personItems, ...orgItems];
  } catch {
    return [];
  }
}

async function fetchMentionables(query: string): Promise<SuggestionItem[]> {
  if (!query.trim()) return [{ id: '__hint__', label: 'Typ om te zoeken...' }];
  try {
    const results = await apiGet<MentionSearchResult[]>('/api/mentions/search', {
      q: query,
      limit: 10,
    });
    return results.map((r) => ({
      id: r.id,
      label: r.label,
      subtitle: r.subtitle ?? r.type,
      mentionType: r.type,
    }));
  } catch {
    return [];
  }
}

// ─── TipTap extensions ──────────────────────────────────────────────────────

const PersonMention = Mention.extend({
  name: 'mention',
  addAttributes() {
    return {
      ...this.parent?.(),
      mentionType: {
        default: 'person',
        parseHTML: (element: HTMLElement) => element.getAttribute('data-mention-type') ?? 'person',
        renderHTML: (attributes: Record<string, unknown>) => ({
          'data-mention-type': attributes.mentionType as string,
        }),
      },
    };
  },
}).configure({
  HTMLAttributes: {
    class: 'mention-person',
  },
  suggestion: {
    ...createSuggestionConfig(fetchPeopleAndOrgs),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    command: ({ editor, range, props }: { editor: Editor; range: { from: number; to: number }; props: any }) => {
      editor
        .chain()
        .focus()
        .insertContentAt(range, [
          {
            type: 'mention',
            attrs: {
              id: props.id,
              label: props.label,
              mentionType: props.mentionType ?? 'person',
            },
          },
          { type: 'text', text: ' ' },
        ])
        .run();
    },
  },
  renderLabel: ({ node }: { node: { attrs: { label?: string } } }) => {
    return `@${node.attrs.label ?? ''}`;
  },
});

const HashtagMention = Mention.extend({
  name: 'hashtagMention',
  addAttributes() {
    return {
      ...this.parent?.(),
      mentionType: {
        default: 'node',
        parseHTML: (element: HTMLElement) => element.getAttribute('data-mention-type') ?? 'node',
        renderHTML: (attributes: Record<string, unknown>) => ({
          'data-mention-type': attributes.mentionType as string,
        }),
      },
    };
  },
}).configure({
  HTMLAttributes: {
    class: 'mention-hashtag',
  },
  suggestion: {
    char: '#',
    ...createSuggestionConfig(fetchMentionables),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    command: ({ editor, range, props }: { editor: Editor; range: { from: number; to: number }; props: any }) => {
      editor
        .chain()
        .focus()
        .insertContentAt(range, [
          {
            type: 'hashtagMention',
            attrs: {
              id: props.id,
              label: props.label,
              mentionType: props.mentionType ?? 'node',
            },
          },
          { type: 'text', text: ' ' },
        ])
        .run();
    },
  },
  renderLabel: ({ node }: { node: { attrs: { label?: string } } }) => {
    return `#${node.attrs.label ?? ''}`;
  },
});

// ─── Helper: parse TipTap JSON or plain text ───────────────────────────────

function parseContent(value: string): object {
  if (!value) {
    return { type: 'doc', content: [{ type: 'paragraph' }] };
  }
  try {
    const parsed = JSON.parse(value);
    if (parsed && parsed.type === 'doc') return parsed;
  } catch {
    // plain text fallback
  }
  return {
    type: 'doc',
    content: [{ type: 'paragraph', content: [{ type: 'text', text: value }] }],
  };
}

// ─── Main Component ─────────────────────────────────────────────────────────

export function RichTextEditor({
  value,
  onChange,
  placeholder = '',
  rows = 3,
  readOnly = false,
  id,
  autoFocus = false,
}: RichTextEditorProps) {
  const initialContent = useRef(parseContent(value));
  const skipUpdate = useRef(false);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
      }),
      Placeholder.configure({ placeholder }),
      PersonMention,
      HashtagMention,
    ],
    content: initialContent.current,
    editable: !readOnly,
    onUpdate: ({ editor }) => {
      if (skipUpdate.current) {
        skipUpdate.current = false;
        return;
      }
      const json = JSON.stringify(editor.getJSON());
      onChange(json);
    },
  });

  // Focus editor when autoFocus is set (delayed to work inside modals)
  useEffect(() => {
    if (autoFocus && editor && !readOnly) {
      requestAnimationFrame(() => editor.commands.focus('end'));
    }
  }, [editor, autoFocus, readOnly]);

  // Sync editable state
  useEffect(() => {
    if (editor) {
      editor.setEditable(!readOnly);
    }
  }, [editor, readOnly]);

  // Sync external value changes (e.g., form reset)
  useEffect(() => {
    if (!editor) return;
    const currentJson = JSON.stringify(editor.getJSON());
    if (value !== currentJson) {
      const newContent = parseContent(value);
      const newJson = JSON.stringify(newContent);
      if (newJson !== currentJson) {
        skipUpdate.current = true;
        editor.commands.setContent(newContent);
      }
    }
  }, [value, editor]);

  const minHeight = `${Math.max(rows * 1.5, 3)}rem`;

  return (
    <div
      id={id}
      className={`rich-text-editor block w-full rounded-xl border border-border bg-white text-sm text-text transition-colors duration-150 focus-within:ring-2 focus-within:ring-primary-500/20 focus-within:border-primary-500 hover:border-border-hover ${
        readOnly ? 'opacity-60 cursor-not-allowed' : ''
      }`}
    >
      <EditorContent
        editor={editor}
        className="px-3.5 py-2.5 prose prose-sm max-w-none focus:outline-none"
        style={{ minHeight }}
      />
      <style>{`
        .rich-text-editor .ProseMirror {
          outline: none;
          min-height: ${minHeight};
        }
        .rich-text-editor .ProseMirror p.is-editor-empty:first-child::before {
          content: attr(data-placeholder);
          float: left;
          color: #9ca3af;
          pointer-events: none;
          height: 0;
        }
        .rich-text-editor .ProseMirror .mention-person {
          background-color: #dbeafe;
          color: #1d4ed8;
          border-radius: 0.25rem;
          padding: 0.1rem 0.3rem;
          font-weight: 500;
          text-decoration: none;
        }
        .rich-text-editor .ProseMirror .mention-person[data-mention-type="organisatie"] {
          background-color: #d1fae5;
          color: #065f46;
        }
        .rich-text-editor .ProseMirror .mention-hashtag {
          background-color: #f1f5f9;
          color: #475569;
          border-radius: 0.25rem;
          padding: 0.1rem 0.3rem;
          font-weight: 500;
          text-decoration: none;
        }
      `}</style>
    </div>
  );
}
