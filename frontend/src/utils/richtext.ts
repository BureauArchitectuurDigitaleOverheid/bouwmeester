/**
 * Extract plain text from a string that may be TipTap/ProseMirror JSON.
 * Returns the original string if it's not JSON.
 */
export function richTextToPlain(value: string | null | undefined): string {
  if (!value) return '';
  try {
    const doc = JSON.parse(value);
    if (doc && doc.type === 'doc') {
      return extractText(doc).trim();
    }
  } catch {
    // Not JSON — return as-is
  }
  return value;
}

interface TipTapNode {
  type: string;
  content?: TipTapNode[];
  text?: string;
  attrs?: Record<string, unknown>;
}

function extractText(node: TipTapNode): string {
  if (node.text) return node.text;
  if (node.type === 'mention' || node.type === 'hashtagMention') {
    const label = node.attrs?.label as string | undefined;
    return label ? `${label}` : '';
  }
  if (!node.content) return '';
  return node.content.map(extractText).join(node.type === 'paragraph' ? ' ' : '');
}
