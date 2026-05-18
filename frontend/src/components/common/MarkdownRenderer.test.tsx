import { describe, it, expect } from 'vitest';
import DOMPurify from 'dompurify';

/**
 * MarkdownRenderer's MermaidBlock pipes the rendered SVG through
 * `DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } })`
 * before injecting it via `dangerouslySetInnerHTML`. Mermaid output is
 * derived from user-supplied Markdown, so a crafted diagram could embed
 * script/event handlers in the SVG. This pins that the SVG profile
 * strips active content while keeping the drawing.
 *
 * The async mermaid.render path is awkward to drive in jsdom; testing
 * the exact sanitize config the component uses is the security-relevant
 * unit and won't go stale when the rendering plumbing changes.
 */

const SVG_OPTS = { USE_PROFILES: { svg: true, svgFilters: true } } as const;
const sanitize = (svg: string) => DOMPurify.sanitize(svg, SVG_OPTS);

describe('MarkdownRenderer Mermaid SVG sanitization', () => {
  it('keeps benign SVG shapes and filters', () => {
    const out = sanitize(
      '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>',
    );
    expect(out).toContain('<svg');
    expect(out).toContain('<rect');
  });

  it('strips a <script> element inside the SVG', () => {
    const out = sanitize(
      '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect/></svg>',
    );
    expect(out).not.toContain('<script');
    expect(out).not.toContain('alert(1)');
    expect(out).toContain('<rect');
  });

  it('strips an onload handler on the svg root', () => {
    const out = sanitize(
      '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect/></svg>',
    );
    expect(out).not.toContain('onload');
    expect(out).not.toContain('alert(1)');
  });

  it('strips a foreignObject script injection vector', () => {
    const out = sanitize(
      '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject>' +
        '<img src=x onerror="alert(1)"></foreignObject></svg>',
    );
    expect(out).not.toContain('onerror');
    expect(out).not.toContain('alert(1)');
  });
});
