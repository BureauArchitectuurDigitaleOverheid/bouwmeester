import { micromark } from 'micromark';

const NUMBERED_LINE = /^\s*\d+[.)]\s+\S/;
const BULLET_LINE = /^\s*[-*•]\s+\S/;

/**
 * Plain text from a mail-client paste often contains a list as visually
 * numbered or bulleted lines (e.g. "1. foo\n2. bar" or "• foo\n• bar").
 * Without help, ProseMirror lands those as bare paragraphs and the
 * structure is lost. This detects whether such a list is present.
 *
 * Heuristic: at least two consecutive list-like lines, or a list-like
 * line that makes up the majority of non-empty lines.
 */
export function looksLikeListPaste(text: string): boolean {
  const lines = text.split('\n');
  let listy = 0;
  let nonEmpty = 0;
  let consecutive = 0;
  let maxConsecutive = 0;
  for (const line of lines) {
    if (!line.trim()) {
      consecutive = 0;
      continue;
    }
    nonEmpty += 1;
    if (NUMBERED_LINE.test(line) || BULLET_LINE.test(line)) {
      listy += 1;
      consecutive += 1;
      if (consecutive > maxConsecutive) maxConsecutive = consecutive;
    } else {
      consecutive = 0;
    }
  }
  if (maxConsecutive >= 2) return true;
  return nonEmpty > 0 && listy / nonEmpty > 0.5;
}

/**
 * Normalise paste content so micromark recognises the list structure
 * regardless of the source client's quirks.
 *
 * - Convert `•` and `1)` style bullets into markdown-friendly equivalents.
 * - Strip leading whitespace on list lines (mail clients often indent).
 * - Collapse Windows line endings.
 */
function normaliseForMarkdown(text: string): string {
  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => {
      const trimmed = line.replace(/^\s+/, '');
      if (/^•\s+/.test(trimmed)) return trimmed.replace(/^•\s+/, '- ');
      if (/^\d+\)\s+/.test(trimmed)) return trimmed.replace(/^(\d+)\)\s+/, '$1. ');
      if (NUMBERED_LINE.test(trimmed) || BULLET_LINE.test(trimmed)) return trimmed;
      return line;
    })
    .join('\n');
}

/**
 * Convert plain text that contains list structure into HTML that
 * ProseMirror can parse into proper `ol`/`ul` nodes. Returns `null`
 * when the text shouldn't be treated as a list paste.
 */
export function listyTextToHtml(text: string): string | null {
  if (!looksLikeListPaste(text)) return null;
  return micromark(normaliseForMarkdown(text));
}
