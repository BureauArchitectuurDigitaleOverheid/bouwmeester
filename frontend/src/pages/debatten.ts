import type { EntityColor } from '@/types';
import type { AankomendDebat, DebatKanaal, DebatStartResult, DebatTeam } from '@/types/debat';

const AMSTERDAM = 'Europe/Amsterdam';

const dayKey = new Intl.DateTimeFormat('sv-SE', {
  timeZone: AMSTERDAM,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});
const dayLabel = new Intl.DateTimeFormat('nl-NL', {
  timeZone: AMSTERDAM,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
});
const time = new Intl.DateTimeFormat('nl-NL', {
  timeZone: AMSTERDAM,
  hour: '2-digit',
  minute: '2-digit',
});

/** `16:30 tot 21:30`, in Dutch time whatever the browser is set to. */
export function formatTijd(debat: AankomendDebat): string {
  if (!debat.aanvang) return '';
  const start = new Date(debat.aanvang);
  const tekst = time.format(start);
  if (!debat.einde) return tekst;
  const end = new Date(debat.einde);
  // An end on another day is not an end time anyone reads as such.
  if (dayKey.format(end) !== dayKey.format(start) || end <= start) return tekst;
  return `${tekst} tot ${time.format(end)}`;
}

/** The line under the subject: time, kind, committee. */
export function formatRegel(debat: AankomendDebat): string {
  return [formatTijd(debat), debat.soort, debat.commissie].filter(Boolean).join(' · ');
}

export interface DebatDag {
  key: string;
  label: string;
  debatten: AankomendDebat[];
}

/**
 * Groups by day in Dutch time, keeping the order the API gave.
 *
 * Debates without a start time end up under their own heading at the end,
 * instead of under 1 January 1970.
 */
export function groepeerPerDag(debatten: AankomendDebat[]): DebatDag[] {
  const dagen = new Map<string, DebatDag>();
  for (const debat of debatten) {
    const start = debat.aanvang ? new Date(debat.aanvang) : null;
    const key = start ? dayKey.format(start) : 'onbekend';
    let dag = dagen.get(key);
    if (!dag) {
      dag = { key, label: start ? dayLabel.format(start) : 'Datum onbekend', debatten: [] };
      dagen.set(key, dag);
    }
    dag.debatten.push(debat);
  }
  return [...dagen.values()];
}

/** On right now: running, or in a break of a debate that is not over. */
export function isNuBezig(debat: AankomendDebat): boolean {
  return debat.stand === 'bezig' || debat.stand === 'geschorst';
}

/**
 * Splits the list in what is on right now and the rest per day.
 *
 * What is on comes first, the one that has run longest on top; without a
 * real start the planned one decides. The rest keeps the order the API gave.
 */
export function verdeelDebatten(debatten: AankomendDebat[]): {
  nu: AankomendDebat[];
  dagen: DebatDag[];
} {
  const since = (debat: AankomendDebat): number => {
    const moment = debat.begonnen_om ?? debat.aanvang;
    // Without any time: after the ones that have one.
    return moment ? new Date(moment).getTime() : Number.POSITIVE_INFINITY;
  };
  const nu = debatten
    .filter(isNuBezig)
    .map((debat, index) => ({ debat, index }))
    // The index keeps the order of the API between two that started together.
    .sort((a, b) => {
      const [sa, sb] = [since(a.debat), since(b.debat)];
      return sa === sb ? a.index - b.index : sa - sb;
    })
    .map(({ debat }) => debat);
  return { nu, dagen: groepeerPerDag(debatten.filter((debat) => !isNuBezig(debat))) };
}

/** The badge that says where a debate stands; none for one that is still to come. */
export function standBadge(debat: AankomendDebat): { label: string; color: EntityColor } | null {
  switch (debat.stand) {
    case 'bezig':
      return { label: 'Nu bezig', color: 'groen' };
    case 'geschorst':
      return { label: 'Geschorst', color: 'geel' };
    case 'afgelopen':
      return { label: 'Afgelopen', color: 'coolgray' };
    default:
      return null;
  }
}

export type KanaalActie = 'stoppen' | 'hervatten';

/**
 * What can be done with the following of a debate in this channel.
 *
 * Stopping for one that is followed. Resuming only for one that was stopped
 * while the debate is not over: a timeline that ended with its debate, or a
 * debate that was cancelled, has nothing left to follow.
 */
export function kanaalActie(debat: AankomendDebat, kanaal: DebatKanaal): KanaalActie | null {
  if (!kanaal.sessie_id) return null;
  if (kanaal.wordt_gevolgd) return 'stoppen';
  if (kanaal.tijdlijn_status === 'afgelopen' && debat.stand !== 'afgelopen') return 'hervatten';
  return null;
}

/** What the bot does with a debate, going by the channels on the row. */
export function volgTekst(debat: AankomendDebat, kanalen: DebatKanaal[]): string | null {
  // Before it starts a channel is simply there; that it will be followed is
  // what the stop button says.
  if (isNuBezig(debat) && kanalen.some((kanaal) => kanaal.wordt_gevolgd)) return 'wordt gevolgd';
  if (kanalen.some((kanaal) => kanaalActie(debat, kanaal) === 'hervatten')) return 'volgen gestopt';
  return null;
}

/**
 * The line under the subject. For a debate that is on: since when it runs
 * instead of when it was planned. Then kind, committee, and what the bot
 * does with it.
 */
export function formatDebatRegel(debat: AankomendDebat, kanalen: DebatKanaal[] = []): string {
  const tijd =
    isNuBezig(debat) && debat.begonnen_om
      ? `Begonnen om ${time.format(new Date(debat.begonnen_om))}`
      : formatTijd(debat);
  return [tijd, debat.soort, debat.commissie, volgTekst(debat, kanalen)].filter(Boolean).join(' · ');
}

/** Matches every word of the query somewhere in subject, kind or committee. */
export function filterDebatten(debatten: AankomendDebat[], query: string): AankomendDebat[] {
  const woorden = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (woorden.length === 0) return debatten;
  return debatten.filter((debat) => {
    const tekst = [debat.onderwerp, debat.soort, debat.commissie, debat.nummer]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return woorden.every((woord) => tekst.includes(woord));
  });
}

/**
 * The team a channel goes into: the chosen one if it is still on offer, or
 * the only one there is. With several teams and no choice there is none.
 *
 * Deliberately no default among several. The first version picked the first
 * team where the bot may create a channel, and a debate channel then landed
 * in a team that had nothing to do with it. Where a channel goes is a choice
 * for the person, not for the sort order.
 */
export function kiesTeam(teams: DebatTeam[], gekozen: string | null): DebatTeam | null {
  const chosen = teams.find((team) => team.team_id === gekozen);
  if (chosen) return chosen;
  return teams.length === 1 ? teams[0] : null;
}

/**
 * The channels to show on a row: the one in the chosen team, or all of them
 * while no team is chosen, so an existing channel is never hidden.
 */
export function zichtbareKanalen(debat: AankomendDebat, teamId: string | null): DebatKanaal[] {
  return teamId === null ? debat.kanalen : debat.kanalen.filter((k) => k.team_id === teamId);
}

const TEAM_KEY = 'bouwmeester.debatten.team';

/** The team chosen last time, in this browser. */
export function leesGekozenTeam(): string | null {
  try {
    return localStorage.getItem(TEAM_KEY);
  } catch {
    // Private mode or blocked storage: the choice just does not survive.
    return null;
  }
}

export function bewaarGekozenTeam(teamId: string): void {
  try {
    localStorage.setItem(TEAM_KEY, teamId);
  } catch {
    // See above.
  }
}

/** What to tell the person who pressed start, and whether it is bad news. */
export function startMelding(
  result: DebatStartResult,
  teamNaam?: string | null,
): { tekst: string; fout: boolean } {
  const kanaal = result.kanaal ? `~${result.kanaal.channel_name}` : 'Het kanaal';
  // Name the team: with several, "in Mattermost" does not say where to look.
  const waar = teamNaam ? `in team ${teamNaam}` : 'in Mattermost';
  switch (result.outcome) {
    case 'created':
      return { tekst: `${kanaal} staat klaar ${waar}.`, fout: false };
    case 'exists':
      return { tekst: `Er was al een kanaal voor dit debat: ${kanaal}.`, fout: false };
    case 'in_progress':
      return { tekst: 'Dit kanaal wordt op dit moment al opgezet.', fout: false };
    default:
      return { tekst: result.melding ?? 'Het kanaal opzetten is niet gelukt.', fout: true };
  }
}
