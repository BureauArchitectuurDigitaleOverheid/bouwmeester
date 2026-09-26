const NUMBERED_LINE = /^\s*\d+[.)]\s+\S/;
const BULLET_LINE = /^\s*[-*•]\s+\S/;

/**
 * Plain text from a mail client often contains a list as visually numbered or
 * bulleted lines ("1. foo\n2. bar", or "• foo\n• bar"). This detects whether
 * such a list is present.
 *
 * Heuristic: at least two consecutive list-like lines, or a list-like line that
 * makes up the majority of non-empty lines.
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
      maxConsecutive = Math.max(maxConsecutive, consecutive);
    } else {
      consecutive = 0;
    }
  }

  if (nonEmpty === 0) return false;
  return maxConsecutive >= 2 || listy / nonEmpty > 0.5;
}

/**
 * Normalise pasted text so the markdown editor recognises the list structure
 * whatever the source client did.
 *
 * - `•` and `1)` become `-` and `1.`, which markdown knows and they do not.
 * - Leading whitespace goes: mail clients indent list lines, and in markdown an
 *   indent of four spaces means a code block instead.
 * - Windows line endings are collapsed.
 */
function normaliseListPaste(text: string): string {
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
 * The markdown for a pasted list, or null when the text is not one.
 *
 * The editor stores markdown, so `1. foo` is already a list. The work left
 * here is the normalisation above: the bullets and the indenting that markdown
 * would otherwise read as something else.
 */
export function listyTextToMarkdown(text: string): string | null {
  if (!looksLikeListPaste(text)) return null;
  return normaliseListPaste(text);
}
