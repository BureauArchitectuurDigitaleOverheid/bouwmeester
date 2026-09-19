import { LeadStage } from '@/types';
import type { EngagementType } from '@/types';

/**
 * Local nldd-tag color per lead stage.
 *
 * `LEAD_STAGE_COLORS` in `src/types` holds raw Tailwind chip classes for the
 * seven stages and is off-limits to edit in this pass (Tailwind-removal
 * scope). This is the presentation-side replacement: the five mid-funnel
 * stages get a distinguishing Rijkshuisstijl hue, since they are just
 * visually distinct labels, while the two stages that carry real structural
 * meaning ("won", "parked") get a semantic role instead, since that meaning
 * matters more than visual variety there.
 */
type NlddTagColor = NonNullable<React.ComponentProps<'nldd-tag'>['color']>;

const STAGE_TAG_COLOR: Record<string, NlddTagColor> = {
  [LeadStage.INBOX]: 'lintblauw',
  [LeadStage.VERKENNEN]: 'hemelblauw',
  [LeadStage.EERSTE_GESPREK]: 'geel',
  [LeadStage.INTERNE_CHECK]: 'oranje',
  [LeadStage.FOLLOW_UP]: 'paars',
  [LeadStage.IN_THE_POCKET]: 'success',
  [LeadStage.KOELKAST]: 'neutral',
};

export function stageTagColor(stage: string): NlddTagColor {
  return STAGE_TAG_COLOR[stage as LeadStage] ?? 'neutral';
}

/**
 * Same idea for `EngagementType` (a fixed 5-value union, unlike
 * `LeadColumn.color`), replacing `ENGAGEMENT_TYPE_COLORS` in `src/types`.
 */
const ENGAGEMENT_TAG_COLOR: Record<EngagementType, NlddTagColor> = {
  intern_oppakken: 'success',
  voorbereiden_eigen_team: 'lintblauw',
  betrokken_houden: 'hemelblauw',
  verkenning: 'oranje',
  nog_te_bepalen: 'neutral',
};

export function engagementTagColor(type: EngagementType): NlddTagColor {
  return ENGAGEMENT_TAG_COLOR[type] ?? 'neutral';
}

/**
 * The closed set `LeadColumn.color` may hold, mirrored from backend
 * `schema.lead_column.LEAD_COLUMN_COLORS` (kept in sync by hand; see
 * migration `54ec9a7df491_lead_column_colors_to_names`, which moved the
 * stored values off raw Tailwind strings and onto these names).
 */
const LEAD_COLUMN_COLORS: ReadonlySet<NlddTagColor> = new Set([
  'neutral',
  'accent',
  'success',
  'warning',
  'critical',
  'lintblauw',
  'donkerblauw',
  'hemelblauw',
  'lichtblauw',
  'paars',
  'violet',
  'robijnrood',
  'roze',
  'rood',
  'oranje',
  'donkergeel',
  'geel',
  'donkerbruin',
  'bruin',
  'donkergroen',
  'groen',
  'mosgroen',
  'mintgroen',
]);

/** A `col.color` from another environment or an older row falls back to
 *  'neutral' rather than rendering nothing. */
export function leadColumnTagColor(color: string): NlddTagColor {
  return (LEAD_COLUMN_COLORS as ReadonlySet<string>).has(color)
    ? (color as NlddTagColor)
    : 'neutral';
}
