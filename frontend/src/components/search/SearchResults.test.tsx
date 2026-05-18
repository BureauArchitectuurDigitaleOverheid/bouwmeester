import { describe, it, expect } from 'vitest';
import DOMPurify from 'dompurify';

/**
 * SearchResults renders `result.highlights` through
 * `DOMPurify.sanitize(h, { ALLOWED_TAGS: ['mark'] })` into a
 * `dangerouslySetInnerHTML` sink. DOMPurify is the only sanitizer in
 * front of that sink, so this pins the security contract: a search
 * highlight containing an XSS payload must come out with the payload
 * stripped and only `<mark>` preserved.
 *
 * These run against the real DOMPurify in jsdom, so they also fail if a
 * future bump regresses the sanitizer (the reason for #321).
 */

const SANITIZE_OPTS = { ALLOWED_TAGS: ['mark'] } as const;
const sanitize = (html: string) => DOMPurify.sanitize(html, SANITIZE_OPTS);

describe('SearchResults highlight sanitization', () => {
  it('keeps a legitimate <mark> highlight intact', () => {
    expect(sanitize('begroting <mark>onderwijs</mark> 2026')).toBe(
      'begroting <mark>onderwijs</mark> 2026',
    );
  });

  it('strips an img/onerror XSS payload', () => {
    const out = sanitize('<img src=x onerror="alert(1)"> <mark>hit</mark>');
    expect(out).not.toContain('onerror');
    expect(out).not.toContain('<img');
    expect(out).toContain('<mark>hit</mark>');
  });

  it('strips a <script> payload', () => {
    const out = sanitize('<script>alert(document.cookie)</script><mark>x</mark>');
    expect(out).not.toContain('<script');
    expect(out).not.toContain('alert(');
    expect(out).toContain('<mark>x</mark>');
  });

  it('strips a javascript: anchor and disallowed tags', () => {
    const out = sanitize('<a href="javascript:alert(1)">click</a><b>bold</b>');
    expect(out).not.toContain('javascript:');
    expect(out).not.toContain('<a');
    expect(out).not.toContain('<b>');
    // text content survives, markup does not
    expect(out).toContain('click');
  });
});
