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
