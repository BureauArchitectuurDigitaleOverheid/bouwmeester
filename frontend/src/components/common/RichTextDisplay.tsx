import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';

interface RichTextDisplayProps {
  content: string | null | undefined;
  fallback?: string;
}

interface TipTapNode {
  type: string;
  content?: TipTapNode[];
  text?: string;
  attrs?: Record<string, unknown>;
  marks?: TipTapMark[];
}

interface TipTapMark {
  type: string;
  attrs?: Record<string, unknown>;
}

function isTipTapJson(value: string): TipTapNode | null {
  try {
    const parsed = JSON.parse(value);
    if (parsed && parsed.type === 'doc') return parsed;
  } catch {
    // Not JSON
  }
  return null;
}

export function RichTextDisplay({ content, fallback = 'Geen beschrijving beschikbaar.' }: RichTextDisplayProps) {
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();

  if (!content) {
    return <p className="text-sm text-text-secondary whitespace-pre-wrap">{fallback}</p>;
  }

  const doc = isTipTapJson(content);
  if (!doc) {
    // Plain text fallback
    return <p className="text-sm text-text-secondary whitespace-pre-wrap">{content}</p>;
  }

  const handlers: MentionHandlers = { openTaskDetail, openNodeDetail };
  return <div className="text-sm text-text-secondary">{renderNodes(doc.content ?? [], handlers)}</div>;
}

interface MentionHandlers {
  openTaskDetail: (id: string) => void;
  openNodeDetail: (id: string) => void;
}

function renderNodes(nodes: TipTapNode[], handlers: MentionHandlers): React.ReactNode[] {
  return nodes.map((node, i) => renderNode(node, i, handlers));
}

function renderNode(node: TipTapNode, key: number, handlers: MentionHandlers): React.ReactNode {
  switch (node.type) {
    case 'paragraph':
      return (
        <p key={key} className="whitespace-pre-wrap mb-1 last:mb-0">
          {node.content ? renderNodes(node.content, handlers) : null}
        </p>
      );

    case 'text':
      return renderText(node, key);

    case 'mention': {
      const id = node.attrs?.id as string | undefined;
      const label = node.attrs?.label as string | undefined;
      return (
        <button
          key={key}
          onClick={() => {
            // Navigate to person detail (if we had one) or just show tooltip
            // For now, we'll keep it as a styled span
          }}
          className="inline bg-blue-50 text-blue-700 rounded px-1 py-0.5 font-medium text-sm hover:bg-blue-100 transition-colors cursor-default"
          title={`Persoon: ${label}`}
          data-person-id={id}
        >
          @{label}
        </button>
      );
    }

    case 'hashtagMention': {
      const id = node.attrs?.id as string | undefined;
      const label = node.attrs?.label as string | undefined;
      // Default to 'node' for legacy mentions that lack mentionType
      const mentionType = (node.attrs?.mentionType as string | undefined) ?? 'node';
      const isClickable = (mentionType === 'node' || mentionType === 'task') && !!id;
      return (
        <button
          key={key}
          onClick={() => {
            if (mentionType === 'node' && id) {
              handlers.openNodeDetail(id);
            } else if (mentionType === 'task' && id) {
              handlers.openTaskDetail(id);
            }
          }}
          className={`inline rounded px-1 py-0.5 font-medium text-sm transition-colors ${
            isClickable
              ? 'bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer'
              : 'bg-slate-100 text-slate-700 cursor-default'
          }`}
          title={`${mentionType}: ${label}`}
        >
          #{label}
        </button>
      );
    }

    case 'hardBreak':
      return <br key={key} />;

    case 'bulletList':
      return (
        <ul key={key} className="list-disc pl-5 mb-1">
          {node.content ? renderNodes(node.content, handlers) : null}
        </ul>
      );

    case 'orderedList':
      return (
        <ol key={key} className="list-decimal pl-5 mb-1">
          {node.content ? renderNodes(node.content, handlers) : null}
        </ol>
      );

    case 'listItem':
      return (
        <li key={key}>
          {node.content ? renderNodes(node.content, handlers) : null}
        </li>
      );

    default:
      // Fallback for unknown types: render content if available
      if (node.content) {
        return <span key={key}>{renderNodes(node.content, handlers)}</span>;
      }
      return null;
  }
}

function renderText(node: TipTapNode, key: number): React.ReactNode {
  let element: React.ReactNode = node.text ?? '';

  if (node.marks) {
    for (const mark of node.marks) {
      switch (mark.type) {
        case 'bold':
          element = <strong key={key}>{element}</strong>;
          break;
        case 'italic':
          element = <em key={key}>{element}</em>;
          break;
        case 'code':
          element = <code key={key} className="bg-gray-100 rounded px-1 py-0.5 text-xs">{element}</code>;
          break;
        case 'strike':
          element = <s key={key}>{element}</s>;
          break;
      }
    }
  }

  return <span key={key}>{element}</span>;
}
