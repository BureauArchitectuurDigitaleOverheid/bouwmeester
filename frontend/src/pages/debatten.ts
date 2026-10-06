import type { EntityColor } from '@/types';
import type {
  AankomendDebat,
  DebatKanaal,
  DebatStartResult,
  DebatTeam,
  GevolgdDebat,
  GevolgdeDebatten,
} from '@/types/debat';

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

/** Whether the bot is listening to this debate right now. */
export function wordtNuGevolgd(debat: AankomendDebat, kanalen: DebatKanaal[]): boolean {
  // Before it starts a channel is simply there; that it will be followed is
  // what the stop button says.
  return isNuBezig(debat) && kanalen.some((kanaal) => kanaal.wordt_gevolgd);
}

/** The badge next to the one for where the debate stands: the bot is listening. */
export function volgBadge(
  debat: AankomendDebat,
  kanalen: DebatKanaal[],
): { label: string; color: EntityColor } | null {
  return wordtNuGevolgd(debat, kanalen) ? { label: 'Wordt gevolgd', color: 'lintblauw' } : null;
}

/**
 * What the line under the subject says about the following: only that it was
 * stopped. That a debate is followed is a badge, see `volgBadge`.
 */
export function volgTekst(debat: AankomendDebat, kanalen: DebatKanaal[]): string | null {
  if (wordtNuGevolgd(debat, kanalen)) return null;
  if (kanalen.some((kanaal) => kanaalActie(debat, kanaal) === 'hervatten')) return 'volgen gestopt';
  return null;
}

/**
 * Whether the row offers to set up a channel.
 *
 * Not for a debate Debat Direct says has ended: the audio and the subtitles
 * of the stream are gone within the hour, so the channel would stay empty.
 */
export function kanStarten(
  debat: AankomendDebat,
  kanalen: DebatKanaal[],
  canStart: boolean,
): boolean {
  return canStart && kanalen.length === 0 && debat.stand !== 'afgelopen';
}

/** What the link to a channel shows: the subject on the row says which debate. */
export const KANAAL_LINK_TEKST = 'Open kanaal';

/**
 * The accessible name of the link to a channel. Starts with what is visible,
 * and carries the channel name the short label leaves out.
 */
export function kanaalLinkLabel(onderwerp: string, kanaal: DebatKanaal): string {
  return `${KANAAL_LINK_TEKST} ~${kanaal.channel_name} van ${onderwerp}`;
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

const dateTime = new Intl.DateTimeFormat('nl-NL', {
  timeZone: AMSTERDAM,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/** `di 6 okt 2026, 16:30`, in Dutch time; with the year, because this list goes back. */
export function formatGevolgdMoment(debat: GevolgdDebat): string {
  return debat.aanvang ? dateTime.format(new Date(debat.aanvang)) : 'Datum onbekend';
}

/** `12 vragen gemarkeerd, 3 open`; nothing when no question was marked. */
export function formatVragen(vragen: number, open: number): string | null {
  if (vragen <= 0) return null;
  const gemarkeerd = `${vragen} ${vragen === 1 ? 'vraag' : 'vragen'} gemarkeerd`;
  return `${gemarkeerd}, ${open > 0 ? open : 'geen'} open`;
}

/** `48 berichten`; nothing for a channel the timeline never wrote in. */
export function formatBerichten(berichten: number): string | null {
  if (berichten <= 0) return null;
  return `${berichten} ${berichten === 1 ? 'bericht' : 'berichten'}`;
}

/** The line under the subject of a followed debate: when, and what came of it. */
export function formatGevolgdRegel(debat: GevolgdDebat): string {
  return [
    formatGevolgdMoment(debat),
    formatBerichten(debat.berichten),
    formatVragen(debat.vragen, debat.vragen_open),
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * The badge for how a followed debate ended. Only for one that was cancelled
 * or moved: a debate that ran to its end and one someone stopped following
 * are stored the same, so neither gets a word here.
 */
export function afloopBadge(debat: GevolgdDebat): { label: string; color: EntityColor } | null {
  return debat.afloop === 'afgelast' ? { label: 'Afgelast of verplaatst', color: 'oranje' } : null;
}

/**
 * The pages read so far as one list, in the order they came.
 *
 * Paging is by offset, and the list shifts when a debate ends between two
 * pages: the same debate can then come twice, and is kept once.
 */
export function gevolgdeDebatten(pages: GevolgdeDebatten[]): GevolgdDebat[] {
  const seen = new Set<string>();
  const debatten: GevolgdDebat[] = [];
  for (const page of pages) {
    for (const debat of page.debatten) {
      if (seen.has(debat.sessie_id)) continue;
      seen.add(debat.sessie_id);
      debatten.push(debat);
    }
  }
  return debatten;
}

/** Where the next page starts, or `undefined` when everything has been read. */
export function volgendeOffset(pages: GevolgdeDebatten[]): number | undefined {
  const last = pages[pages.length - 1];
  if (!last || last.debatten.length === 0) return undefined;
  const read = last.offset + last.debatten.length;
  return read < last.totaal ? read : undefined;
}

/** Matches every word of the query somewhere in subject, nummer or channel name. */
export function filterGevolgd(debatten: GevolgdDebat[], query: string): GevolgdDebat[] {
  const woorden = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (woorden.length === 0) return debatten;
  return debatten.filter((debat) => {
    const tekst = [debat.onderwerp, debat.nummer, debat.kanaal.channel_name]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return woorden.every((woord) => tekst.includes(woord));
  });
}
