import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AankomendDebat, DebatKanaal, DebatStartResult } from '@/types/debat';
import {
  filterDebatten,
  formatDebatRegel,
  formatRegel,
  formatTijd,
  groepeerPerDag,
  bewaarGekozenTeam,
  isNuBezig,
  kanaalActie,
  kiesTeam,
  leesGekozenTeam,
  standBadge,
  verdeelDebatten,
  volgTekst,
  zichtbareKanalen,
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
    stand: null,
    begonnen_om: null,
    ...overrides,
  };
}

/** A channel the bot follows, unless the overrides say otherwise. */
function kanaal(overrides: Partial<DebatKanaal> = {}): DebatKanaal {
  return {
    team_id: 't',
    channel_name: 'debat-x-6-okt',
    channel_url: null,
    sessie_id: 's1',
    tijdlijn_status: 'loopt',
    wordt_gevolgd: true,
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

describe('kiesTeam', () => {
  const dicht = { team_id: 'dicht', team_name: 'Dicht', can_create_channel: false };
  const open = { team_id: 'open', team_name: 'Open', can_create_channel: true };

  it('keeps the chosen team, also one where no channel can be made', () => {
    // Its existing channels have to stay visible.
    expect(kiesTeam([open, dicht], 'dicht')).toBe(dicht);
  });

  it('picks no team by itself when there are several', () => {
    // A channel once landed in the first team of the list this way.
    expect(kiesTeam([open, dicht], null)).toBeNull();
    expect(kiesTeam([dicht, open], null)).toBeNull();
  });

  it('takes the only team there is', () => {
    expect(kiesTeam([open], null)).toBe(open);
  });

  it('ignores a remembered choice that is no longer on offer', () => {
    expect(kiesTeam([open, dicht], 'weg')).toBeNull();
    expect(kiesTeam([open], 'weg')).toBe(open);
  });

  it('is null without teams', () => {
    expect(kiesTeam([], 'x')).toBeNull();
  });
});

describe('zichtbareKanalen', () => {
  const a = kanaal({ team_id: 'a', channel_name: 'debat-a' });
  const b = kanaal({ team_id: 'b', channel_name: 'debat-b' });

  it('shows the channel of the chosen team', () => {
    expect(zichtbareKanalen(debat({ kanalen: [a, b] }), 'b')).toEqual([b]);
  });

  it('shows none when the chosen team has no channel yet', () => {
    // So the button appears: this debate can still be started there.
    expect(zichtbareKanalen(debat({ kanalen: [a] }), 'b')).toEqual([]);
  });

  it('shows every channel while no team is chosen', () => {
    expect(zichtbareKanalen(debat({ kanalen: [a, b] }), null)).toEqual([a, b]);
  });
});

describe('the remembered team', () => {
  /** A stand-in for the browser's storage; the test environment has none. */
  function stubStorage(overrides: Partial<Storage> = {}) {
    const items = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => items.get(key) ?? null,
      setItem: (key: string, value: string) => void items.set(key, value),
      ...overrides,
    });
  }

  afterEach(() => vi.unstubAllGlobals());

  it('survives a reload', () => {
    stubStorage();
    expect(leesGekozenTeam()).toBeNull();
    bewaarGekozenTeam('team-x');
    expect(leesGekozenTeam()).toBe('team-x');
  });

  it('does not break the page when storage is blocked', () => {
    const blocked = () => {
      throw new Error('blocked');
    };
    stubStorage({ getItem: blocked, setItem: blocked });
    expect(leesGekozenTeam()).toBeNull();
    expect(() => bewaarGekozenTeam('team-x')).not.toThrow();
  });

  it('does not break the page when there is no storage at all', () => {
    vi.stubGlobal('localStorage', undefined);
    expect(leesGekozenTeam()).toBeNull();
    expect(() => bewaarGekozenTeam('team-x')).not.toThrow();
  });
});

describe('startMelding', () => {
  const result = (overrides: Partial<DebatStartResult>): DebatStartResult => ({
    outcome: 'created',
    melding: null,
    kanaal: kanaal(),
    ...overrides,
  });

  it('names the channel when it was created', () => {
    expect(startMelding(result({}))).toEqual({
      tekst: '~debat-x-6-okt staat klaar in Mattermost.',
      fout: false,
    });
  });

  it('names the team, so it is clear where the channel is', () => {
    expect(startMelding(result({}), 'NLDD').tekst).toBe(
      '~debat-x-6-okt staat klaar in team NLDD.',
    );
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

describe('isNuBezig', () => {
  it.each([
    ['bezig', true],
    ['geschorst', true],
    ['niet_begonnen', false],
    ['afgelopen', false],
    [null, false],
  ] as const)('%s is %s', (stand, verwacht) => {
    expect(isNuBezig(debat({ stand }))).toBe(verwacht);
  });
});

describe('verdeelDebatten', () => {
  const ids = (debatten: AankomendDebat[]) => debatten.map((d) => d.activiteit_id);

  it('puts what is on right now above the days, and nowhere else', () => {
    const { nu, dagen } = verdeelDebatten([
      debat({ activiteit_id: 'straks' }),
      debat({ activiteit_id: 'nu', stand: 'bezig', begonnen_om: '2026-10-06T16:31:00+02:00' }),
      debat({ activiteit_id: 'morgen', aanvang: '2026-10-07T10:00:00+02:00' }),
    ]);

    expect(ids(nu)).toEqual(['nu']);
    expect(dagen.map((dag) => [dag.key, ids(dag.debatten)])).toEqual([
      ['2026-10-06', ['straks']],
      ['2026-10-07', ['morgen']],
    ]);
  });

  it('counts a suspended debate as on', () => {
    const { nu, dagen } = verdeelDebatten([debat({ stand: 'geschorst' })]);
    expect(nu).toHaveLength(1);
    expect(dagen).toEqual([]);
  });

  it('leaves a debate that is over under its day', () => {
    const { nu, dagen } = verdeelDebatten([debat({ stand: 'afgelopen' })]);
    expect(nu).toEqual([]);
    expect(dagen).toHaveLength(1);
  });

  it('shows the one that has run longest first', () => {
    const { nu } = verdeelDebatten([
      debat({ activiteit_id: 'later', stand: 'bezig', begonnen_om: '2026-10-06T16:40:00+02:00' }),
      debat({ activiteit_id: 'eerder', stand: 'bezig', begonnen_om: '2026-10-06T10:02:00+02:00' }),
    ]);
    expect(ids(nu)).toEqual(['eerder', 'later']);
  });

  it('goes by the real start, not the planned one', () => {
    const { nu } = verdeelDebatten([
      // Planned first, started last.
      debat({
        activiteit_id: 'te-laat',
        stand: 'bezig',
        aanvang: '2026-10-06T10:00:00+02:00',
        begonnen_om: '2026-10-06T12:30:00+02:00',
      }),
      debat({
        activiteit_id: 'op-tijd',
        stand: 'bezig',
        aanvang: '2026-10-06T11:00:00+02:00',
        begonnen_om: '2026-10-06T11:01:00+02:00',
      }),
    ]);
    expect(ids(nu)).toEqual(['op-tijd', 'te-laat']);
  });

  it('falls back on the planned start, and puts one without any time last', () => {
    const { nu } = verdeelDebatten([
      debat({ activiteit_id: 'zonder', stand: 'bezig', aanvang: null }),
      debat({ activiteit_id: 'gepland', stand: 'bezig', aanvang: '2026-10-06T16:30:00+02:00' }),
      debat({ activiteit_id: 'echt', stand: 'bezig', begonnen_om: '2026-10-06T09:00:00+02:00' }),
    ]);
    expect(ids(nu)).toEqual(['echt', 'gepland', 'zonder']);
  });

  it('keeps the order of the API between two that started together', () => {
    const samen = { stand: 'bezig', begonnen_om: '2026-10-06T10:00:00+02:00' } as const;
    const { nu } = verdeelDebatten([
      debat({ activiteit_id: 'b', ...samen }),
      debat({ activiteit_id: 'a', ...samen }),
      debat({ activiteit_id: 'c', ...samen }),
    ]);
    expect(ids(nu)).toEqual(['b', 'a', 'c']);
  });

  it('compares moments, not the strings they came in', () => {
    const { nu } = verdeelDebatten([
      // 09:30 UTC is 11:30 in the Kamer: later than 11:00+02:00.
      debat({ activiteit_id: 'utc', stand: 'bezig', begonnen_om: '2026-10-06T09:30:00Z' }),
      debat({ activiteit_id: 'lokaal', stand: 'bezig', begonnen_om: '2026-10-06T11:00:00+02:00' }),
    ]);
    expect(ids(nu)).toEqual(['lokaal', 'utc']);
  });

  it('does not change the list it was given', () => {
    const lijst = [
      debat({ activiteit_id: 'later', stand: 'bezig', begonnen_om: '2026-10-06T16:40:00+02:00' }),
      debat({ activiteit_id: 'eerder', stand: 'bezig', begonnen_om: '2026-10-06T10:02:00+02:00' }),
    ];
    verdeelDebatten(lijst);
    expect(ids(lijst)).toEqual(['later', 'eerder']);
  });

  it('is empty for an empty list', () => {
    expect(verdeelDebatten([])).toEqual({ nu: [], dagen: [] });
  });
});

describe('standBadge', () => {
  it.each([
    ['bezig', { label: 'Nu bezig', color: 'groen' }],
    ['geschorst', { label: 'Geschorst', color: 'geel' }],
    ['afgelopen', { label: 'Afgelopen', color: 'coolgray' }],
  ] as const)('%s gets a badge', (stand, verwacht) => {
    expect(standBadge(debat({ stand }))).toEqual(verwacht);
  });

  it.each(['niet_begonnen', null] as const)('%s gets none', (stand) => {
    expect(standBadge(debat({ stand }))).toBeNull();
  });
});

describe('kanaalActie', () => {
  it.each([null, 'gekoppeld', 'loopt'] as const)(
    'offers stopping for a followed sessie in status %s',
    (tijdlijn_status) => {
      expect(kanaalActie(debat(), kanaal({ tijdlijn_status }))).toBe('stoppen');
    },
  );

  it('offers stopping also when the debate has not started', () => {
    expect(kanaalActie(debat({ stand: 'niet_begonnen' }), kanaal({ tijdlijn_status: null }))).toBe(
      'stoppen',
    );
  });

  it.each(['bezig', 'geschorst', 'niet_begonnen', null] as const)(
    'offers resuming for a stopped sessie while the debate is %s',
    (stand) => {
      const gestopt = kanaal({ tijdlijn_status: 'afgelopen', wordt_gevolgd: false });
      expect(kanaalActie(debat({ stand }), gestopt)).toBe('hervatten');
    },
  );

  it('offers nothing when the debate is over', () => {
    const gestopt = kanaal({ tijdlijn_status: 'afgelopen', wordt_gevolgd: false });
    expect(kanaalActie(debat({ stand: 'afgelopen' }), gestopt)).toBeNull();
  });

  it('offers nothing for a cancelled debate', () => {
    const afgelast = kanaal({ tijdlijn_status: 'afgelast', wordt_gevolgd: false });
    expect(kanaalActie(debat({ stand: 'bezig' }), afgelast)).toBeNull();
  });

  it('offers nothing without a sessie to act on', () => {
    expect(kanaalActie(debat(), kanaal({ sessie_id: null }))).toBeNull();
    expect(
      kanaalActie(
        debat(),
        kanaal({ sessie_id: null, tijdlijn_status: 'afgelopen', wordt_gevolgd: false }),
      ),
    ).toBeNull();
  });

  it('goes by what the backend says is followed, not by the status alone', () => {
    // `null` is the status of a sessie that is followed, and also what a
    // missing value looks like.
    expect(kanaalActie(debat(), kanaal({ tijdlijn_status: null, wordt_gevolgd: false }))).toBeNull();
  });
});

describe('volgTekst', () => {
  const gestopt = kanaal({ tijdlijn_status: 'afgelopen', wordt_gevolgd: false });

  it('says a running debate is followed', () => {
    expect(volgTekst(debat({ stand: 'bezig' }), [kanaal()])).toBe('wordt gevolgd');
    expect(volgTekst(debat({ stand: 'geschorst' }), [kanaal()])).toBe('wordt gevolgd');
  });

  it('says nothing about a debate that is still to come', () => {
    expect(volgTekst(debat({ stand: 'niet_begonnen' }), [kanaal()])).toBeNull();
    expect(volgTekst(debat(), [kanaal({ tijdlijn_status: null })])).toBeNull();
  });

  it('says so when following was stopped', () => {
    expect(volgTekst(debat({ stand: 'bezig' }), [gestopt])).toBe('volgen gestopt');
    expect(volgTekst(debat(), [gestopt])).toBe('volgen gestopt');
  });

  it('says nothing about a timeline that ended with its debate', () => {
    expect(volgTekst(debat({ stand: 'afgelopen' }), [gestopt])).toBeNull();
  });

  it('prefers the channel that is followed when another was stopped', () => {
    expect(volgTekst(debat({ stand: 'bezig' }), [gestopt, kanaal({ team_id: 'u' })])).toBe(
      'wordt gevolgd',
    );
  });

  it('says nothing without a channel', () => {
    expect(volgTekst(debat({ stand: 'bezig' }), [])).toBeNull();
  });
});

describe('formatDebatRegel', () => {
  it('is the plain line for a debate that is still to come', () => {
    expect(formatDebatRegel(debat())).toBe(formatRegel(debat()));
  });

  it('says since when a running debate runs, in Dutch time', () => {
    const nu = debat({ stand: 'bezig', begonnen_om: '2026-10-06T14:34:00Z' });
    expect(formatDebatRegel(nu)).toBe(
      'Begonnen om 16:34 · Commissiedebat · vaste commissie voor Digitale Zaken',
    );
  });

  it('says the same for a suspended one', () => {
    const nu = debat({ stand: 'geschorst', begonnen_om: '2026-10-06T16:34:00+02:00' });
    expect(formatDebatRegel(nu)).toMatch(/^Begonnen om 16:34 · /);
  });

  it('shows the planned time while the real start is unknown', () => {
    expect(formatDebatRegel(debat({ stand: 'bezig' }))).toMatch(/^16:30 tot 21:30 · /);
  });

  it('keeps the planned time for a debate that is over', () => {
    const voorbij = debat({ stand: 'afgelopen', begonnen_om: '2026-10-06T16:34:00+02:00' });
    expect(formatDebatRegel(voorbij)).toMatch(/^16:30 tot 21:30 · /);
  });

  it('ends with what the bot does', () => {
    const nu = debat({ stand: 'bezig', begonnen_om: '2026-10-06T16:34:00+02:00' });
    expect(formatDebatRegel(nu, [kanaal()])).toMatch(/ · wordt gevolgd$/);
    expect(
      formatDebatRegel(debat(), [kanaal({ tijdlijn_status: 'afgelopen', wordt_gevolgd: false })]),
    ).toMatch(/ · volgen gestopt$/);
  });
});
