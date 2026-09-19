import { describe, it, expect } from 'vitest';
import { mentionToMarkdown, parseMention, MENTION_SCHEMES } from './mentions';

/**
 * This format is written in two places: here, by the editor, and in
 * `backend/bouwmeester/core/tiptap_markdown.py`, by the migration that
 * converted the TipTap documents. The cases below are the same ones
 * `backend/tests/test_tiptap_markdown.py` asserts, so the two cannot drift
 * apart without a test failing on one side.
 */
describe('mention format', () => {
  it('writes a person mention as a link with the design system its own scheme', () => {
    expect(mentionToMarkdown('person', '3fa9c1e2', 'Anne Schuth')).toBe(
      '[@Anne Schuth](user:3fa9c1e2)',
    );
  });

  it('writes our own schemes for the other kinds', () => {
    expect(mentionToMarkdown('organisatie', 'abc', 'BZK')).toBe('[@BZK](org:abc)');
    expect(mentionToMarkdown('node', 'n1', 'Dossier')).toBe('[#Dossier](node:n1)');
    expect(mentionToMarkdown('task', 't1', 'Taak')).toBe('[#Taak](task:t1)');
  });

  it('escapes brackets in a label', () => {
    // A display name comes out of the database; an unescaped `]` would close
    // the link early and let the rest be read as markdown of its own.
    expect(mentionToMarkdown('person', 'x', 'Jan] (evil) [')).toBe(
      '[@Jan\\] (evil) \\[](user:x)',
    );
  });

  it('percent-encodes the id', () => {
    expect(mentionToMarkdown('person', 'a b/c', 'X')).toBe('[@X](user:a%20b%2Fc)');
  });

  it('round-trips', () => {
    for (const kind of Object.keys(MENTION_SCHEMES) as (keyof typeof MENTION_SCHEMES)[]) {
      const written = mentionToMarkdown(kind, 'id-1', 'Naam met ] erin');
      const href = /\]\(([^)]*)\)/.exec(written)![1];
      const text = /^\[(.*)\]\(/.exec(written)![1];
      expect(parseMention(href, text)).toEqual({ kind, id: 'id-1', label: 'Naam met ] erin' });
    }
  });

  it('reads a token written before the id was encoded', () => {
    expect(parseMention('user:plain-id', '@Anne')).toEqual({
      kind: 'person',
      id: 'plain-id',
      label: 'Anne',
    });
  });

  it('leaves an ordinary link alone', () => {
    expect(parseMention('https://rijksoverheid.nl', 'Rijksoverheid')).toBeNull();
    expect(parseMention('mailto:a@b.nl', 'Mail')).toBeNull();
    expect(parseMention('bm://node/123', 'Node')).toBeNull();
  });

  it('rejects a scheme with no id', () => {
    expect(parseMention('user:', '@Leeg')).toBeNull();
  });
});
