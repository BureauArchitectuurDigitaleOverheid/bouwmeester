import { describe, it, expect } from 'vitest';
import { looksLikeListPaste, listyTextToHtml } from './richTextPaste';

describe('looksLikeListPaste', () => {
  it('detects numbered lists', () => {
    expect(looksLikeListPaste('1. eerste\n2. tweede\n3. derde')).toBe(true);
  });

  it('detects bullet lists with -', () => {
    expect(looksLikeListPaste('- alpha\n- bravo')).toBe(true);
  });

  it('detects bullet lists with •', () => {
    expect(looksLikeListPaste('• alpha\n• bravo')).toBe(true);
  });

  it('detects 1) 2) style numbered lists', () => {
    expect(looksLikeListPaste('1) eerste\n2) tweede')).toBe(true);
  });

  it('tolerates leading whitespace from indented mail clients', () => {
    expect(looksLikeListPaste('   1. eerste\n   2. tweede')).toBe(true);
  });

  it('detects lists separated by blank lines', () => {
    expect(looksLikeListPaste('1. eerste\n\n2. tweede\n\n3. derde')).toBe(true);
  });

  it('rejects plain prose', () => {
    expect(looksLikeListPaste('Gewone tekst zonder lijst.\nMet meerdere regels.')).toBe(false);
  });

  it('rejects empty input', () => {
    expect(looksLikeListPaste('')).toBe(false);
  });

  it('rejects a single isolated list-like line surrounded by prose', () => {
    expect(
      looksLikeListPaste('Hier staat veel tekst.\n1. een eenzaam ding\nEn nog meer tekst hier.\nOok een regel.'),
    ).toBe(false);
  });

  it('accepts a list with surrounding prose', () => {
    expect(
      looksLikeListPaste('Inleiding.\n\n1. punt een\n2. punt twee\n3. punt drie\n\nAfsluiting.'),
    ).toBe(true);
  });
});

describe('listyTextToHtml', () => {
  it('returns null for non-list text', () => {
    expect(listyTextToHtml('Gewone tekst.')).toBeNull();
  });

  it('converts a numbered list to <ol>', () => {
    const html = listyTextToHtml('1. eerste\n2. tweede\n3. derde');
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>eerste</li>');
    expect(html).toContain('<li>tweede</li>');
    expect(html).toContain('<li>derde</li>');
  });

  it('converts a bullet list to <ul>', () => {
    const html = listyTextToHtml('- alpha\n- bravo');
    expect(html).toContain('<ul>');
    expect(html).toContain('<li>alpha</li>');
    expect(html).toContain('<li>bravo</li>');
  });

  it('converts • bullets', () => {
    const html = listyTextToHtml('• alpha\n• bravo');
    expect(html).toContain('<ul>');
    expect(html).toContain('<li>alpha</li>');
  });

  it('converts 1) 2) numbered style', () => {
    const html = listyTextToHtml('1) eerste\n2) tweede');
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>eerste</li>');
  });

  it('handles indented list lines from mail clients', () => {
    const html = listyTextToHtml('    1. eerste\n    2. tweede');
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>eerste</li>');
    expect(html).toContain('<li>tweede</li>');
  });

  it('preserves prose around the list', () => {
    const html = listyTextToHtml(
      'Inleiding.\n\n1. punt een\n2. punt twee\n\nAfsluiting.',
    );
    expect(html).toContain('<p>Inleiding.</p>');
    expect(html).toContain('<ol>');
    expect(html).toContain('<p>Afsluiting.</p>');
  });

  it('handles Windows line endings', () => {
    const html = listyTextToHtml('1. eerste\r\n2. tweede');
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>eerste</li>');
    expect(html).toContain('<li>tweede</li>');
  });

  it('preserves the realistic Abram-style mail content', () => {
    const input =
      '1. Pilot van Abv met de SVB. (actie Abv)\n' +
      '2. Pilot van Abv met DUO. (actie Abv)\n' +
      '3. Een student doet onderzoek. (actie RR)';
    const html = listyTextToHtml(input);
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>Pilot van Abv met de SVB. (actie Abv)</li>');
    expect(html).toContain('<li>Een student doet onderzoek. (actie RR)</li>');
  });
});
