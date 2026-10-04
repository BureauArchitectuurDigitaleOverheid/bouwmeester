import { describe, expect, it } from 'vitest';
import type { AankomendDebat, DebatStartResult } from '@/types/debat';
import {
  filterDebatten,
  formatRegel,
  formatTijd,
  groepeerPerDag,
  startbareTeams,
  startMelding,
} from './debatten';

function debat(overrides: Partial<AankomendDebat> = {}): AankomendDebat {
  return {
    activiteit_id: 'a1',
    nummer: '2026A05428',
    soort: 'Commissiedebat',
    onderwerp: 'Digitaliserende overheid',
    aanvang: '2026-10-06T16:30:00+02:00',
    einde: '2026-10-06T21:30:00+02:00',
    commissie: 'vaste commissie voor Digitale Zaken',
    agenda_url: null,
    kanalen: [],
    ...overrides,
  };
}

describe('formatTijd', () => {
  it('shows start and end', () => {
    expect(formatTijd(debat())).toBe('16:30 tot 21:30');
  });

  it('shows Dutch time for a UTC timestamp', () => {
    // 14:30 UTC in October is 16:30 in the Kamer, whatever the browser is on.
    expect(formatTijd(debat({ aanvang: '2026-10-06T14:30:00Z', einde: null }))).toBe('16:30');
  });

  it('leaves out an end on another day', () => {
    expect(formatTijd(debat({ einde: '2026-10-07T01:00:00+02:00' }))).toBe('16:30');
  });

  it('is empty without a start', () => {
    expect(formatTijd(debat({ aanvang: null }))).toBe('');
  });
});

describe('formatRegel', () => {
  it('joins time, kind and committee', () => {
    expect(formatRegel(debat())).toBe(
      '16:30 tot 21:30 · Commissiedebat · vaste commissie voor Digitale Zaken',
    );
  });

  it('skips what is missing instead of leaving a gap', () => {
    expect(formatRegel(debat({ commissie: null, aanvang: null }))).toBe('Commissiedebat');
  });
});

describe('groepeerPerDag', () => {
  it('groups by Dutch day and keeps the order', () => {
    const dagen = groepeerPerDag([
      debat({ activiteit_id: 'a' }),
      debat({ activiteit_id: 'b', aanvang: '2026-10-06T19:00:00+02:00' }),
      debat({ activiteit_id: 'c', aanvang: '2026-10-07T10:00:00+02:00' }),
    ]);
    expect(dagen.map((d) => d.label)).toEqual(['dinsdag 6 oktober', 'woensdag 7 oktober']);
    expect(dagen[0].debatten.map((d) => d.activiteit_id)).toEqual(['a', 'b']);
  });

  it('puts a late-evening UTC time on the Dutch day it falls on', () => {
    // 22:30 UTC on the 6th is 00:30 on the 7th in the Kamer.
    const dagen = groepeerPerDag([debat({ aanvang: '2026-10-06T22:30:00Z' })]);
    expect(dagen[0].label).toBe('woensdag 7 oktober');
  });

  it('does not file a debate without a date under 1970', () => {
    const dagen = groepeerPerDag([debat({ aanvang: null })]);
    expect(dagen[0].label).toBe('Datum onbekend');
  });
});

describe('filterDebatten', () => {
  const lijst = [
    debat({ activiteit_id: 'a' }),
    debat({ activiteit_id: 'b', onderwerp: 'Leefomgeving', commissie: 'vaste commissie voor I&W' }),
  ];

  it('returns everything for an empty query', () => {
    expect(filterDebatten(lijst, '  ')).toHaveLength(2);
  });

  it('matches the subject, ignoring case', () => {
    expect(filterDebatten(lijst, 'LEEFOM').map((d) => d.activiteit_id)).toEqual(['b']);
  });

  it('matches the committee', () => {
    expect(filterDebatten(lijst, 'digitale zaken').map((d) => d.activiteit_id)).toEqual(['a']);
  });

  it('needs every word, in any field', () => {
    expect(filterDebatten(lijst, 'overheid commissiedebat')).toHaveLength(1);
    expect(filterDebatten(lijst, 'overheid leefomgeving')).toHaveLength(0);
  });

  it('finds a debate by its nummer', () => {
    expect(filterDebatten(lijst, '2026a05428')).toHaveLength(2);
  });
});

describe('startbareTeams', () => {
  it('keeps only teams the bot may create a channel in', () => {
    const teams = [
      { team_id: 'a', team_name: 'A', can_create_channel: true },
      { team_id: 'b', team_name: 'B', can_create_channel: false },
    ];
    expect(startbareTeams(teams).map((t) => t.team_id)).toEqual(['a']);
  });
});

describe('startMelding', () => {
  const kanaal = { team_id: 't', channel_name: 'debat-x-6-okt', channel_url: null };
  const result = (overrides: Partial<DebatStartResult>): DebatStartResult => ({
    outcome: 'created',
    melding: null,
    kanaal,
    ...overrides,
  });

  it('names the channel when it was created', () => {
    expect(startMelding(result({}))).toEqual({
      tekst: '~debat-x-6-okt staat klaar in Mattermost.',
      fout: false,
    });
  });

  it('is not an error when the channel was already there', () => {
    const melding = startMelding(result({ outcome: 'exists' }));
    expect(melding.fout).toBe(false);
    expect(melding.tekst).toContain('~debat-x-6-okt');
  });

  it('is not an error while someone else is setting it up', () => {
    expect(startMelding(result({ outcome: 'in_progress', kanaal: null })).fout).toBe(false);
  });

  it.each(['refused', 'failed'] as const)('shows the reason for %s as an error', (outcome) => {
    expect(
      startMelding(result({ outcome, kanaal: null, melding: 'Deze vergadering is geannuleerd.' })),
    ).toEqual({ tekst: 'Deze vergadering is geannuleerd.', fout: true });
  });

  it('still says something when the reason is missing', () => {
    const melding = startMelding(result({ outcome: 'failed', kanaal: null }));
    expect(melding.fout).toBe(true);
    expect(melding.tekst).not.toBe('');
  });
});
