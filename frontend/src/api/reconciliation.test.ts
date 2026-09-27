import { describe, expect, it } from 'vitest';
import { mergeResultMessage, type MergeResult } from './reconciliation';

const result = (eigenaarsrechten: number, plaatsingen: number): MergeResult => ({
  status: 'merged',
  doelrij_id: 'x',
  rewritten: {},
  eigenaarsrechten_verwijderd: eigenaarsrechten,
  plaatsingen_onbevestigd: plaatsingen,
});

describe('mergeResultMessage', () => {
  it('says only that the merge finished when no trust was taken away', () => {
    expect(mergeResultMessage(result(0, 0))).toBe('Merge voltooid.');
  });

  it('names the removed owner grants and unconfirmed placements', () => {
    expect(mergeResultMessage(result(3, 2))).toBe(
      'Merge voltooid: 3 eigenaarsrechten verwijderd, 2 plaatsingen wachten op bevestiging.',
    );
    expect(mergeResultMessage(result(0, 1))).toBe('Merge voltooid: 1 plaatsingen wachten op bevestiging.');
  });
});
