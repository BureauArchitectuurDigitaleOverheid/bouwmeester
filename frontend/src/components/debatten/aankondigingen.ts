import type { EntityColor } from '@/types';
import type { AankomendDebat, DebatAankondiging } from '@/types/debat';
import { filterDebatten } from '@/pages/debatten';

const AMSTERDAM = 'Europe/Amsterdam';

const dayKey = new Intl.DateTimeFormat('sv-SE', {
  timeZone: AMSTERDAM,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const moment = new Intl.DateTimeFormat('nl-NL', {
  timeZone: AMSTERDAM,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
});

/** `dinsdag 6 oktober om 16:30`, in Dutch time whatever the browser is set to. */
export function formatMoment(aanvang: string | null): string {
  return aanvang ? moment.format(new Date(aanvang)) : 'Datum onbekend';
}

/** The line under the subject: when, what kind, which committee. */
export function formatAankondigingRegel(
  debat: Pick<DebatAankondiging, 'aanvang' | 'soort' | 'commissie'>,
): string {
  return [formatMoment(debat.aanvang), debat.soort, debat.commissie].filter(Boolean).join(' · ');
}

/**
 * The badge for a debate that is not simply coming up. None for one that is
 * announced and waiting for its day: that is what being on the list says.
 *
 * "Vandaag" goes by the date and not by the reminder having gone out: a
 * debate stays on the list for a day after it started, and the reminder of
 * yesterday does not make it today.
 */
export function aankondigingBadge(
  debat: Pick<DebatAankondiging, 'stand' | 'aanvang'>,
  nu: Date = new Date(),
): { label: string; color: EntityColor } | null {
  if (debat.stand === 'afgelast') return { label: 'Afgelast of verplaatst', color: 'oranje' };
  if (!debat.aanvang) return null;
  const dag = dayKey.format(new Date(debat.aanvang));
  const vandaag = dayKey.format(nu);
  if (dag === vandaag) return { label: 'Vandaag', color: 'groen' };
  if (dag < vandaag) return { label: 'Voorbij', color: 'coolgray' };
  return null;
}

/** From how many characters a search is a search. */
export const ZOEK_MIN = 2;
/** How many meetings a search shows at most. */
export const ZOEK_MAX = 8;

export interface Zoekresultaat {
  debat: AankomendDebat;
  /** Already on the list of this initiatief. */
  aangekondigd: boolean;
}

/**
 * The meetings that match the search, soonest first as the agenda gives
 * them, and whether each was announced already. Nothing for a search that
 * is too short to mean anything.
 */
export function zoekDebatten(
  debatten: AankomendDebat[],
  query: string,
  aankondigingen: Pick<DebatAankondiging, 'activiteit_id'>[],
): { resultaten: Zoekresultaat[]; meer: number } {
  if (query.trim().length < ZOEK_MIN) return { resultaten: [], meer: 0 };
  const gevonden = filterDebatten(debatten, query);
  const bekend = new Set(aankondigingen.map((a) => a.activiteit_id));
  return {
    resultaten: gevonden
      .slice(0, ZOEK_MAX)
      .map((debat) => ({ debat, aangekondigd: bekend.has(debat.activiteit_id) })),
    meer: Math.max(0, gevonden.length - ZOEK_MAX),
  };
}

/** What the toast says after announcing. */
export function aankondigMelding(gepostIn: number | null): string {
  if (!gepostIn) {
    return 'Het debat staat op de lijst. Er is niets gepost: dit initiatief heeft geen kanaal dat bereikbaar is.';
  }
  return gepostIn === 1
    ? 'Het debat is aangekondigd in 1 kanaal.'
    : `Het debat is aangekondigd in ${gepostIn} kanalen.`;
}
