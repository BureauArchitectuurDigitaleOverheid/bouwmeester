import { useState, useMemo, useCallback, useRef } from 'react';
import { format, isToday, isYesterday, subDays, subMonths } from 'date-fns';
import { nl } from 'date-fns/locale';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { NlddButton } from '@/components/nldd/NlddLink';
import { Icon } from '@/components/nldd/Icon';
import { useNlddEvent } from '@/components/nldd/events';
import { LeadMetricsBar } from './LeadMetricsBar';
import { useLeadTimeline } from '@/hooks/useLeads';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import {
  LeadStage,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
} from '@/types';
import type { LeadTimelineEvent } from '@/types';

// -- Period presets --
type PeriodKey = 'week' | 'month' | 'quarter' | 'all';

const PERIOD_OPTIONS: { label: string; value: PeriodKey }[] = [
  { label: 'Afgelopen week', value: 'week' },
  { label: 'Afgelopen maand', value: 'month' },
  { label: 'Afgelopen kwartaal', value: 'quarter' },
  { label: 'Alles', value: 'all' },
];

function periodToDates(period: PeriodKey): { date_from?: string; date_to?: string } {
  const now = new Date();
  switch (period) {
    case 'week':
      return { date_from: subDays(now, 7).toISOString().slice(0, 10) };
    case 'month':
      return { date_from: subMonths(now, 1).toISOString().slice(0, 10) };
    case 'quarter':
      return { date_from: subMonths(now, 3).toISOString().slice(0, 10) };
    case 'all':
      return {};
  }
}

// -- Event type icons (nldd-icon names) --
const EVENT_ICONS: Record<string, string> = {
  meeting: 'calendar-event',
  call: 'at',
  email: 'envelope',
  note: 'message-rectangle-text',
  created: 'plus',
  stage_change: 'arrow-right',
};

function eventIconName(type: string): string {
  return EVENT_ICONS[type] ?? 'sparkles';
}

// -- Date group label --
function formatDateGroupLabel(dateStr: string): string {
  // Parse as noon local time to avoid timezone-induced off-by-one
  const date = new Date(dateStr + 'T12:00:00');
  if (isToday(date)) return 'Vandaag';
  if (isYesterday(date)) return 'Gisteren';
  return format(date, 'd MMMM yyyy', { locale: nl });
}

// -- Group events by date --
function groupEventsByDate(events: LeadTimelineEvent[]): Map<string, LeadTimelineEvent[]> {
  const groups = new Map<string, LeadTimelineEvent[]>();
  for (const event of events) {
    const day = format(new Date(event.timestamp), 'yyyy-MM-dd');
    const existing = groups.get(day);
    if (existing) {
      existing.push(event);
    } else {
      groups.set(day, [event]);
    }
  }
  return groups;
}

// -- Stage badge --
// LEAD_STAGE_COLORS holds raw Tailwind chip classes for seven stages, not one
// of the five semantic roles; collapsing them would lose the per-stage
// distinctness, and src/types is off-limits to edit in this pass (see the
// same call in LeadMetricsBar.tsx). The chip stays a styled span rather than
// an nldd-tag with a guessed color.
function StageBadge({ stage }: { stage: string }) {
  const stageKey = stage as LeadStage;
  const colors = LEAD_STAGE_COLORS[stageKey] ?? 'bg-gray-100 text-gray-800';
  const label = LEAD_STAGE_LABELS[stageKey] ?? stage;
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors}`}
    >
      {label}
    </span>
  );
}

// -- Event description --
function EventDescription({ event }: { event: LeadTimelineEvent }) {
  switch (event.event_type) {
    case 'created':
      return (
        <div className="mt-2 flex items-center gap-2 text-sm text-text-secondary">
          <span>Nieuwe lead aangemaakt</span>
          <StageBadge stage={event.stage} />
        </div>
      );

    case 'stage_change':
      return (
        <div className="mt-2 flex items-center gap-2 text-sm flex-wrap">
          {event.from_stage && <StageBadge stage={event.from_stage} />}
          <Icon name="arrow-right" size="sm" className="text-text-secondary shrink-0" />
          {event.to_stage && <StageBadge stage={event.to_stage} />}
        </div>
      );

    case 'note':
      return event.content ? (
        <div className="mt-2 line-clamp-2 [&_p]:m-0 [&_p]:leading-snug">
          <RichTextDisplay content={event.content} fallback="" />
        </div>
      ) : null;

    case 'meeting':
    case 'call':
    case 'email':
      return (
        <div className="mt-2 flex items-start gap-2 text-sm text-text-secondary">
          <Icon name={eventIconName(event.event_type)} size="sm" />
          {event.content ? (
            <div className="line-clamp-2 flex-1 [&_p]:m-0 [&_p]:leading-snug">
              <RichTextDisplay content={event.content} fallback="" />
            </div>
          ) : (
            <span className="line-clamp-2">{getActivityLabel(event.event_type)}</span>
          )}
        </div>
      );

    default:
      return event.content ? (
        <div className="mt-2 line-clamp-2 [&_p]:m-0 [&_p]:leading-snug">
          <RichTextDisplay content={event.content} fallback="" />
        </div>
      ) : null;
  }
}

function getActivityLabel(type: string): string {
  switch (type) {
    case 'meeting': return 'Meeting vastgelegd';
    case 'call': return 'Telefoongesprek vastgelegd';
    case 'email': return 'E-mail vastgelegd';
    default: return 'Activiteit';
  }
}

// -- Single timeline event row --
//
// This is a feed of distinct events across many leads, not a single entity's
// progress toward a known end, so nldd-timeline-track-cell's `status`
// (past/current/future relative to where *you* are) doesn't carry real
// meaning here — every row is simply "past". It still earns its place as the
// per-row dot-and-line lane the design already had: `variant="major"`,
// `status="past"` on every row, `position="between"` throughout (the date
// group headers already provide the visual break the design used to mark
// with a sticky label, so the track itself stays one continuous line).
function TimelineEventCard({
  event,
  onClickLead,
}: {
  event: LeadTimelineEvent;
  onClickLead: (leadId: string) => void;
}) {
  const time = format(new Date(event.timestamp), 'HH:mm');
  const ref = useRef<HTMLElement>(null);
  const handleClick = useCallback(() => onClickLead(event.lead_id), [onClickLead, event.lead_id]);
  useNlddEvent(ref, 'click', handleClick);

  return (
    <nldd-list-item>
      <nldd-timeline-track-cell status="past" variant="major" position="between" />
      <nldd-list-item-segment ref={ref} button width="full" accessible-label={event.lead_title}>
        <div className="w-full text-left">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-0.5">
                <nldd-text size="xs" color="secondary" className="tabular-nums">{time}</nldd-text>
                <Icon name={eventIconName(event.event_type)} size="sm" className="opacity-50" />
              </div>
              <nldd-title-cell text={event.lead_title} size={6} />
              {event.organization && (
                <nldd-text size="sm" color="secondary" className="truncate block">
                  {event.organization}
                </nldd-text>
              )}
            </div>
            <StageBadge stage={event.stage} />
          </div>

          <EventDescription event={event} />

          {(event.actor_naam || event.assignee_naam) && (
            <div className="mt-2.5 flex items-center gap-3 text-xs text-text-secondary">
              {event.actor_naam && <span>Door {event.actor_naam}</span>}
              {event.assignee_naam && event.assignee_naam !== event.actor_naam && (
                <span className="opacity-60">Verantwoordelijk: {event.assignee_naam}</span>
              )}
            </div>
          )}
        </div>
      </nldd-list-item-segment>
    </nldd-list-item>
  );
}

// -- Main timeline view --
interface LeadTimelineViewProps {
  searchQuery?: string;
  initiatiefId: string;
  assigneeId?: string;
  stageFilter?: string;
}

export function LeadTimelineView({
  searchQuery = '',
  initiatiefId,
  assigneeId,
  stageFilter,
}: LeadTimelineViewProps) {
  const [period, setPeriod] = useState<PeriodKey>('month');
  const [displayLimit, setDisplayLimit] = useState(50);

  const { openLeadDetail } = useLeadDetail();

  const dates = periodToDates(period);
  const queryParams = useMemo(
    () => ({
      ...dates,
      ...(stageFilter ? { stage: stageFilter } : {}),
      ...(assigneeId ? { assignee_id: assigneeId } : {}),
      ...(initiatiefId ? { initiatief_id: initiatiefId } : {}),
      limit: 500,
    }),
    [dates.date_from, dates.date_to, stageFilter, assigneeId, initiatiefId],
  );

  const { data, isLoading } = useLeadTimeline(queryParams);

  const events = data?.events ?? [];
  const totalEvents = data?.total ?? 0;

  // Apply client-side search
  const filteredEvents = useMemo(() => {
    if (!searchQuery) return events;
    const q = searchQuery.toLowerCase();
    return events.filter((e) =>
      e.lead_title.toLowerCase().includes(q) ||
      (e.organization ?? '').toLowerCase().includes(q) ||
      (e.actor_naam ?? '').toLowerCase().includes(q) ||
      (e.content ?? '').toLowerCase().includes(q)
    );
  }, [events, searchQuery]);

  const displayedEvents = filteredEvents.slice(0, displayLimit);
  const hasMore = displayedEvents.length < filteredEvents.length;

  const groupedEvents = useMemo(
    () => groupEventsByDate(displayedEvents),
    [displayedEvents],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <LeadMetricsBar />
      </div>

      {/* Period selector + event count */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-0.5 rounded-lg bg-gray-100 p-0.5">
          {PERIOD_OPTIONS.map((opt) => (
            <NlddButton
              key={opt.value}
              size="sm"
              variant={period === opt.value ? 'neutral-base' : 'neutral-transparent'}
              text={opt.label}
              onClick={() => setPeriod(opt.value)}
            />
          ))}
        </div>

        {!isLoading && (
          <nldd-text size="xs" color="secondary" className="ml-auto">
            {totalEvents} {totalEvents === 1 ? 'activiteit' : 'activiteiten'}
          </nldd-text>
        )}
      </div>

      {/* Timeline */}
      {isLoading ? (
        <LoadingSpinner className="py-12" />
      ) : filteredEvents.length === 0 ? (
        <EmptyTimeline />
      ) : (
        <div className="pb-8">
          {Array.from(groupedEvents.entries()).map(([dateKey, dayEvents]) => (
            <div key={dateKey} className="mb-2">
              {/* Date header */}
              <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm py-2.5">
                <nldd-text size="sm" weight="medium" color="secondary" className="tracking-wide">
                  {formatDateGroupLabel(dateKey)}
                </nldd-text>
              </div>

              {/* Events for this date */}
              <nldd-list variant="simple" dividers="never" accessible-label={`Activiteit op ${formatDateGroupLabel(dateKey)}`}>
                {dayEvents.map((event) => (
                  <TimelineEventCard
                    key={event.id}
                    event={event}
                    onClickLead={openLeadDetail}
                  />
                ))}
              </nldd-list>
            </div>
          ))}

          {/* Load more */}
          {hasMore && (
            <div className="pt-4">
              <NlddButton
                text={`Meer laden (${filteredEvents.length - displayLimit} overig)`}
                startIcon="chevron-down"
                variant="secondary"
                size="sm"
                onClick={() => setDisplayLimit((prev) => prev + 50)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EmptyTimeline() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-4">
        <Icon name="calendar-event" size="xl" className="text-gray-400" />
      </div>
      <nldd-title-cell text="Nog geen activiteit" size={5} horizontal-alignment="center" />
      <nldd-text size="sm" color="secondary" className="max-w-sm">
        Maak een nieuwe lead aan om te beginnen. Alle activiteit verschijnt hier in chronologische volgorde.
      </nldd-text>
    </div>
  );
}
