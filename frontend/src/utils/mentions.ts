/**
 * How a mention is written in the markdown the editor stores.
 *
 * A mention is a markdown link carrying a scheme:
 *
 *     [@Anne Schuth](user:3fa9c1e2-...)
 *     [#DigiD](node:0303d844-...)
 *
 * `user:` is the design system's own prefix for its built-in @-mention
 * (MENTION_HREF_PREFIX in nldd-text-editor). The other three are ours, because
 * this app mentions more kinds of thing than a person. They follow the same
 * shape deliberately: still valid markdown, and still a working link anywhere
 * the scheme is not understood, which is what makes it safe to store in a
 * column other code reads.
 *
 * The backend writes this same format in `core/tiptap_markdown.py`. The two
 * must agree: a scheme changed here has to change there, and everything
 * already stored has to be rewritten to match.
 */

/** Mention kind -> URL scheme. Keep in step with _MENTION_SCHEMES in the backend. */
export const MENTION_SCHEMES = {
  person: 'user',
  organisatie: 'org',
  node: 'node',
  task: 'task',
} as const;

export type MentionKind = keyof typeof MENTION_SCHEMES;

/** Scheme -> kind, for reading. */
export const SCHEME_TO_KIND: Record<string, MentionKind> = Object.fromEntries(
  Object.entries(MENTION_SCHEMES).map(([kind, scheme]) => [scheme, kind as MentionKind]),
) as Record<string, MentionKind>;

/** The sigil shown in front of the label. */
export function mentionSigil(kind: MentionKind): '@' | '#' {
  return kind === 'person' || kind === 'organisatie' ? '@' : '#';
}

/**
 * Escape what would end the link text early.
 *
 * A label is a display name out of the database. Without this, a name holding
 * `]` closes the link and the rest of it is read as markdown of its own, which
 * is a way to smuggle a link into someone else's description.
 */
function escapeLabel(label: string): string {
  return label.replace(/\\/g, '\\\\').replace(/\[/g, '\\[').replace(/\]/g, '\\]');
}

function unescapeLabel(label: string): string {
  return label.replace(/\\([[\]\\])/g, '$1');
}

/** Write one mention. */
export function mentionToMarkdown(kind: MentionKind, id: string, label: string): string {
  const scheme = MENTION_SCHEMES[kind];
  return `[${mentionSigil(kind)}${escapeLabel(label)}](${scheme}:${encodeURIComponent(id)})`;
}

export interface ParsedMention {
  kind: MentionKind;
  id: string;
  /** Without the sigil. */
  label: string;
}

/**
 * Read a mention out of a markdown link's href and text.
 *
 * Returns null for an ordinary link, which is the common case: most links in a
 * description are just links.
 */
export function parseMention(href: string, text: string): ParsedMention | null {
  const match = /^([a-z]+):(.*)$/.exec(href);
  if (!match) return null;

  const kind = SCHEME_TO_KIND[match[1]];
  if (!kind) return null;

  let id = match[2];
  try {
    id = decodeURIComponent(id);
  } catch {
    // A token written by hand before the encoding existed: take it as it is.
  }
  if (!id) return null;

  const label = unescapeLabel(text.replace(/^[@#]/, ''));
  return { kind, id, label };
}
