import { describe, it, expect } from 'vitest';
import { looksLikeListPaste, listyTextToMarkdown } from './richTextPaste';

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

describe('listyTextToMarkdown', () => {
  it('returns null for non-list text', () => {
    expect(listyTextToMarkdown('Gewone tekst.')).toBeNull();
  });

  it('leaves a markdown list as it is', () => {
    expect(listyTextToMarkdown('1. eerste\n2. tweede\n3. derde')).toBe(
      '1. eerste\n2. tweede\n3. derde',
    );
    expect(listyTextToMarkdown('- alpha\n- bravo')).toBe('- alpha\n- bravo');
  });

  it('converts bullets markdown does not know', () => {
    expect(listyTextToMarkdown('• alpha\n• bravo')).toBe('- alpha\n- bravo');
  });

  it('converts the 1) 2) numbering style', () => {
    expect(listyTextToMarkdown('1) eerste\n2) tweede')).toBe('1. eerste\n2. tweede');
  });

  it('strips the indent mail clients add', () => {
    // Four spaces of indent is a code block in markdown, not a list.
    expect(listyTextToMarkdown('    1. eerste\n    2. tweede')).toBe(
      '1. eerste\n2. tweede',
    );
  });

  it('preserves prose around the list', () => {
    expect(
      listyTextToMarkdown('Inleiding.\n\n1. punt een\n2. punt twee\n\nAfsluiting.'),
    ).toBe('Inleiding.\n\n1. punt een\n2. punt twee\n\nAfsluiting.');
  });

  it('collapses windows line endings', () => {
    expect(listyTextToMarkdown('- alpha\r\n- bravo')).toBe('- alpha\n- bravo');
  });
});
