import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';

// Regex to detect URLs in plain text.
// Matches http(s) URLs, then trims common trailing sentence punctuation that
// is unlikely to be part of the URL itself.
const URL_REGEX_RAW = /(https?:\/\/[^\s<>)"'\]]+)/;
const URL_REGEX_RAW_GLOBAL = new RegExp(URL_REGEX_RAW.source, 'g');
const TRAILING_PUNCT = /[.,;:!?]+$/;

/** Return true when href is a safe URL (http/https only). */
function isSafeHref(href: string): boolean {
  try {
    const url = new URL(href);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

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
  const navigate = useNavigate();
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();

  if (!content) {
    return <p className="text-sm text-text-secondary whitespace-pre-wrap">{fallback}</p>;
  }

  const doc = isTipTapJson(content);
  if (!doc) {
    // Plain text fallback — auto-linkify URLs
    return <p className="text-sm text-text-secondary whitespace-pre-wrap">{linkifyText(content)}</p>;
  }

  const handlers: MentionHandlers = { openTaskDetail, openNodeDetail, navigate };
  return <div className="text-sm text-text-secondary">{renderNodes(doc.content ?? [], handlers)}</div>;
}

interface MentionHandlers {
  openTaskDetail: (id: string) => void;
  openNodeDetail: (id: string) => void;
  navigate: (path: string) => void;
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
      const mentionType = (node.attrs?.mentionType as string | undefined) ?? 'person';
      const isOrg = mentionType === 'organisatie';
      return (
        <button
          key={key}
          onClick={() => {
            if (isOrg && id) {
              handlers.navigate(`/organisatie?eenheid=${id}`);
            }
          }}
          className={`inline rounded px-1 py-0.5 font-medium text-sm transition-colors ${
            isOrg
              ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 cursor-pointer'
              : 'bg-blue-50 text-blue-700 hover:bg-blue-100 cursor-default'
          }`}
          title={isOrg ? `Afdeling: ${label}` : `Persoon: ${label}`}
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

    case 'heading': {
      const level = (node.attrs?.level as number) ?? 2;
      const Tag = level === 2 ? 'h2' : 'h3';
      const className = level === 2
        ? 'text-lg font-semibold mt-3 mb-1'
        : 'text-base font-semibold mt-2 mb-1';
      return (
        <Tag key={key} className={className}>
          {node.content ? renderNodes(node.content, handlers) : null}
        </Tag>
      );
    }

    case 'blockquote':
      return (
        <blockquote key={key} className="border-l-3 border-gray-300 pl-3 text-gray-500 my-2">
          {node.content ? renderNodes(node.content, handlers) : null}
        </blockquote>
      );

    case 'codeBlock':
      return (
        <pre key={key} className="bg-gray-100 rounded-md px-3 py-2 my-2 font-mono text-xs overflow-x-auto">
          <code>{node.content?.map((c) => c.text ?? '').join('\n')}</code>
        </pre>
      );

    case 'horizontalRule':
      return <hr key={key} className="border-t border-gray-200 my-3" />;

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
  const hasLinkMark = node.marks?.some((m) => m.type === 'link');

  // Auto-linkify plain text that has no explicit link mark
  let element: React.ReactNode = hasLinkMark
    ? (node.text ?? '')
    : linkifyText(node.text ?? '');

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
        case 'link': {
          const href = mark.attrs?.href as string | undefined;
          if (href && isSafeHref(href)) {
            element = (
              <a
                key={key}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-600 underline hover:text-primary-800 break-all"
              >
                {element}
              </a>
            );
          }
          break;
        }
      }
    }
  }

  return <span key={key}>{element}</span>;
}

/**
 * Split text on URLs and return a mix of strings and <a> elements.
 * Trailing sentence punctuation (.,;:!?) is stripped from matched URLs
 * and appended as plain text so "Visit https://example.com." works correctly.
 */
function linkifyText(text: string): React.ReactNode {
  const parts = text.split(URL_REGEX_RAW_GLOBAL);
  if (parts.length === 1) return text; // no URLs found

  const result: React.ReactNode[] = [];
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (URL_REGEX_RAW.test(part)) {
      // Strip trailing punctuation that likely belongs to the sentence, not the URL
      const trimmed = part.replace(TRAILING_PUNCT, '');
      const trailing = part.slice(trimmed.length);
      result.push(
        <a
          key={`l${i}`}
          href={trimmed}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary-600 underline hover:text-primary-800 break-all"
        >
          {trimmed}
        </a>,
      );
      if (trailing) {
        result.push(<React.Fragment key={`t${i}`}>{trailing}</React.Fragment>);
      }
    } else {
      result.push(<React.Fragment key={`p${i}`}>{part}</React.Fragment>);
    }
  }
  return result;
}
