import { describe, expect, it } from 'vitest';
import type { AankomendDebat } from '@/types/debat';
import {
  ZOEK_MAX,
  aankondigMelding,
  aankondigingBadge,
  formatAankondigingRegel,
  formatMoment,
  zoekDebatten,
} from './aankondigingen';

function debat(overrides: Partial<AankomendDebat> = {}): AankomendDebat {
  return {
    activiteit_id: 'a1',
    nummer: '2026A05428',
    soort: 'Commissiedebat',
    onderwerp: 'Digitaliserende overheid',
    aanvang: '2026-10-06T14:30:00Z',
    einde: '2026-10-06T17:30:00Z',
    commissie: 'vaste commissie voor Digitale Zaken',
    agenda_url: null,
    kanalen: [],
    stand: null,
    begonnen_om: null,
    ...overrides,
  };
}

describe('formatMoment', () => {
  it('writes the moment in Dutch time', () => {
    expect(formatMoment('2026-10-06T14:30:00Z')).toBe('dinsdag 6 oktober om 16:30');
  });

  it('says so when there is no date', () => {
    expect(formatMoment(null)).toBe('Datum onbekend');
  });
});

describe('formatAankondigingRegel', () => {
  it('joins when, kind and committee', () => {
    expect(
      formatAankondigingRegel({
        aanvang: '2026-10-06T14:30:00Z',
        soort: 'Commissiedebat',
        commissie: 'vaste commissie voor Digitale Zaken',
      }),
    ).toBe('dinsdag 6 oktober om 16:30 · Commissiedebat · vaste commissie voor Digitale Zaken');
  });

  it('leaves out what is not known', () => {
    expect(formatAankondigingRegel({ aanvang: null, soort: null, commissie: null })).toBe(
      'Datum onbekend',
    );
  });
});

describe('aankondigingBadge', () => {
  const aanvang = '2026-10-06T14:30:00Z';

  it('has none for a debate that waits for its day', () => {
    const nu = new Date('2026-10-05T10:00:00Z');
    expect(aankondigingBadge({ stand: 'aangekondigd', aanvang }, nu)).toBeNull();
  });

  it('says today on the day itself, reminded or not', () => {
    const nu = new Date('2026-10-06T07:00:00Z');
    expect(aankondigingBadge({ stand: 'herinnerd', aanvang }, nu)?.label).toBe('Vandaag');
    expect(aankondigingBadge({ stand: 'aangekondigd', aanvang }, nu)?.label).toBe('Vandaag');
  });

  it('does not call yesterday today because the reminder went out', () => {
    const nu = new Date('2026-10-07T08:00:00Z');
    expect(aankondigingBadge({ stand: 'herinnerd', aanvang }, nu)?.label).toBe('Voorbij');
  });

  it('goes by the Dutch day, not the day in UTC', () => {
    // 23:30 UTC on the 5th is 01:30 on the 6th in Amsterdam.
    const nu = new Date('2026-10-05T23:30:00Z');
    expect(aankondigingBadge({ stand: 'aangekondigd', aanvang }, nu)?.label).toBe('Vandaag');
  });

  it('marks what is off whatever the date', () => {
    const nu = new Date('2026-10-01T10:00:00Z');
    expect(aankondigingBadge({ stand: 'afgelast', aanvang }, nu)?.label).toBe(
      'Afgelast of verplaatst',
    );
  });

  it('has none without a date', () => {
    expect(aankondigingBadge({ stand: 'aangekondigd', aanvang: null })).toBeNull();
  });
});

describe('zoekDebatten', () => {
  const agenda = [
    debat({ activiteit_id: 'a1', onderwerp: 'Digitaliserende overheid' }),
    debat({ activiteit_id: 'a2', onderwerp: 'Leefomgeving', commissie: 'I&W' }),
  ];

  it('shows nothing for a search that is too short', () => {
    expect(zoekDebatten(agenda, ' d ', [])).toEqual({ resultaten: [], meer: 0 });
  });

  it('finds on subject and marks what was announced already', () => {
    const { resultaten } = zoekDebatten(agenda, 'digital', [{ activiteit_id: 'a1' }]);

    expect(resultaten).toEqual([{ debat: agenda[0], aangekondigd: true }]);
  });

  it('does not mark a debate that another activiteit was announced for', () => {
    const { resultaten } = zoekDebatten(agenda, 'leefomgeving', [{ activiteit_id: 'a1' }]);

    expect(resultaten.map((r) => r.aangekondigd)).toEqual([false]);
  });

  it('caps the list and says how many more there are', () => {
    const veel = Array.from({ length: ZOEK_MAX + 3 }, (_, i) =>
      debat({ activiteit_id: `a${i}`, onderwerp: `Begroting ${i}` }),
    );

    const { resultaten, meer } = zoekDebatten(veel, 'begroting', []);

    expect(resultaten).toHaveLength(ZOEK_MAX);
    expect(resultaten[0].debat.activiteit_id).toBe('a0');
    expect(meer).toBe(3);
  });
});

describe('aankondigMelding', () => {
  it('counts the channels', () => {
    expect(aankondigMelding(1)).toBe('Het debat is aangekondigd in 1 kanaal.');
    expect(aankondigMelding(3)).toBe('Het debat is aangekondigd in 3 kanalen.');
  });

  it('says that nothing was posted when there was no channel', () => {
    expect(aankondigMelding(0)).toContain('Er is niets gepost');
    expect(aankondigMelding(null)).toContain('Er is niets gepost');
  });
});
