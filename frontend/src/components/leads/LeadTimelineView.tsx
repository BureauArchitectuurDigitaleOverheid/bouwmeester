import { useState, useMemo } from 'react';
import {
  ArrowRight,
  MessageSquare,
  Phone,
  Mail,
  CalendarDays,
  Plus,
  ChevronDown,
  Sparkles,
} from 'lucide-react';
import { format, isToday, isYesterday, subDays, subMonths } from 'date-fns';
import { nl } from 'date-fns/locale';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { LeadMetricsBar } from './LeadMetricsBar';
import { useLeadTimeline } from '@/hooks/useLeads';
import { usePeople } from '@/hooks/usePeople';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
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

// -- Event dot colors --
const EVENT_DOT_COLORS: Record<string, string> = {
  created: '#10B981',
  stage_change: '#3B82F6',
  note: '#6B7280',
  meeting: '#8B5CF6',
  call: '#F59E0B',
  email: '#06B6D4',
};

const EVENT_DOT_RING_COLORS: Record<string, string> = {
  created: 'ring-green-100',
  stage_change: 'ring-blue-100',
  note: 'ring-gray-100',
  meeting: 'ring-purple-100',
  call: 'ring-yellow-100',
  email: 'ring-cyan-100',
};

// -- Event type icons --
function EventIcon({ type }: { type: string }) {
  const cls = 'h-3.5 w-3.5';
  switch (type) {
    case 'meeting':
      return <CalendarDays className={cls} />;
    case 'call':
      return <Phone className={cls} />;
    case 'email':
      return <Mail className={cls} />;
    case 'note':
      return <MessageSquare className={cls} />;
    case 'created':
      return <Plus className={cls} />;
    case 'stage_change':
      return <ArrowRight className={cls} />;
    default:
      return <Sparkles className={cls} />;
  }
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
          <ArrowRight className="h-3.5 w-3.5 text-text-secondary shrink-0" />
          {event.to_stage && <StageBadge stage={event.to_stage} />}
        </div>
      );

    case 'note':
      return event.content ? (
        <p className="mt-2 text-sm text-text-secondary line-clamp-2">
          {event.content}
        </p>
      ) : null;

    case 'meeting':
    case 'call':
    case 'email':
      return (
        <div className="mt-2 flex items-start gap-2 text-sm text-text-secondary">
          <EventIcon type={event.event_type} />
          <span className="line-clamp-2">{event.content ?? getActivityLabel(event.event_type)}</span>
        </div>
      );

    default:
      return event.content ? (
        <p className="mt-2 text-sm text-text-secondary line-clamp-2">
          {event.content}
        </p>
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

// -- Single timeline event card --
function TimelineEventCard({
  event,
  onClickLead,
}: {
  event: LeadTimelineEvent;
  onClickLead: (leadId: string) => void;
}) {
  const time = format(new Date(event.timestamp), 'HH:mm');
  const dotColor = EVENT_DOT_COLORS[event.event_type] ?? '#6B7280';
  const ringColor = EVENT_DOT_RING_COLORS[event.event_type] ?? 'ring-gray-100';

  return (
    <div className="relative flex items-start gap-4 pl-14 py-2 group">
      {/* Timeline dot */}
      <div
        className={`absolute left-[18px] w-3.5 h-3.5 rounded-full ring-4 ${ringColor} z-10 transition-transform group-hover:scale-125`}
        style={{ backgroundColor: dotColor }}
      />

      {/* Card */}
      <div
        className="flex-1 bg-white rounded-xl border border-border p-4 hover:shadow-md transition-all duration-200 cursor-pointer hover:border-gray-300"
        onClick={() => onClickLead(event.lead_id)}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-xs text-text-secondary tabular-nums">{time}</span>
              <span className="text-xs text-text-secondary opacity-50">
                <EventIcon type={event.event_type} />
              </span>
            </div>
            <h4
              className="font-medium text-text truncate hover:text-primary-600 transition-colors"
              title={event.lead_title}
            >
              {event.lead_title}
            </h4>
            {event.organization && (
              <p className="text-sm text-text-secondary truncate">{event.organization}</p>
            )}
          </div>
          <StageBadge stage={event.stage} />
        </div>

        <EventDescription event={event} />

        {(event.actor_naam || event.assignee_naam) && (
          <div className="mt-2.5 flex items-center gap-3 text-xs text-text-secondary">
            {event.actor_naam && (
              <span>Door {event.actor_naam}</span>
            )}
            {event.assignee_naam && event.assignee_naam !== event.actor_naam && (
              <span className="opacity-60">Verantwoordelijk: {event.assignee_naam}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// -- Main timeline view --
export function LeadTimelineView() {
  const [period, setPeriod] = useState<PeriodKey>('month');
  const [filterStage, setFilterStage] = useState('');
  const [filterAssignee, setFilterAssignee] = useState('');
  const [displayLimit, setDisplayLimit] = useState(50);

  const { data: people } = usePeople();
  const { currentPerson } = useCurrentPerson();
  const { openLeadDetail } = useLeadDetail();

  const dates = periodToDates(period);
  const queryParams = useMemo(
    () => ({
      ...dates,
      ...(filterStage ? { stage: filterStage } : {}),
      ...(filterAssignee ? { assignee_id: filterAssignee } : {}),
      limit: 500,
    }),
    [dates.date_from, dates.date_to, filterStage, filterAssignee],
  );

  const { data, isLoading } = useLeadTimeline(queryParams);

  const events = data?.events ?? [];
  const totalEvents = data?.total ?? 0;
  const displayedEvents = events.slice(0, displayLimit);
  const hasMore = displayedEvents.length < events.length;

  const groupedEvents = useMemo(
    () => groupEventsByDate(displayedEvents),
    [displayedEvents],
  );

  const hasActiveFilters = filterStage || filterAssignee;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <LeadMetricsBar />
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Period selector */}
        <div className="flex items-center gap-0.5 rounded-lg bg-gray-100 p-0.5">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setPeriod(opt.value)}
              className={`px-3 py-1.5 rounded-md text-sm transition-all duration-150 ${
                period === opt.value
                  ? 'bg-white shadow-sm font-medium text-text'
                  : 'text-text-secondary hover:text-text'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Stage filter */}
        <select
          value={filterStage}
          onChange={(e) => setFilterStage(e.target.value)}
          className="rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:border-primary-400"
        >
          <option value="">Alle fases</option>
          {Object.values(LeadStage).map((s) => (
            <option key={s} value={s}>
              {LEAD_STAGE_LABELS[s]}
            </option>
          ))}
        </select>

        {/* Assignee filter */}
        <select
          value={filterAssignee}
          onChange={(e) => setFilterAssignee(e.target.value)}
          className="rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:border-primary-400"
        >
          <option value="">Alle personen</option>
          {currentPerson && (
            <option value={currentPerson.id}>
              Mijn leads ({currentPerson.naam})
            </option>
          )}
          {people
            ?.filter((p) => p.is_active && p.id !== currentPerson?.id)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.naam}
              </option>
            ))}
        </select>

        {/* Clear filters */}
        {hasActiveFilters && (
          <button
            onClick={() => {
              setFilterStage('');
              setFilterAssignee('');
            }}
            className="text-sm text-text-secondary hover:text-text transition-colors"
          >
            Filters wissen
          </button>
        )}

        {/* Event count */}
        {!isLoading && (
          <span className="ml-auto text-xs text-text-secondary">
            {totalEvents} {totalEvents === 1 ? 'activiteit' : 'activiteiten'}
          </span>
        )}
      </div>

      {/* Timeline */}
      {isLoading ? (
        <LoadingSpinner className="py-12" />
      ) : events.length === 0 ? (
        <EmptyTimeline />
      ) : (
        <div className="relative pb-8">
          {/* Vertical timeline line */}
          <div className="absolute left-6 top-4 bottom-0 w-0.5 bg-gradient-to-b from-gray-300 via-gray-200 to-transparent" />

          {Array.from(groupedEvents.entries()).map(([dateKey, dayEvents]) => (
            <div key={dateKey} className="mb-2">
              {/* Date header */}
              <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-sm py-2.5 pl-14">
                <h3 className="text-sm font-semibold text-text-secondary tracking-wide">
                  {formatDateGroupLabel(dateKey)}
                </h3>
              </div>

              {/* Events for this date */}
              {dayEvents.map((event) => (
                <TimelineEventCard
                  key={event.id}
                  event={event}
                  onClickLead={openLeadDetail}
                />
              ))}
            </div>
          ))}

          {/* Load more */}
          {hasMore && (
            <div className="pl-14 pt-4">
              <button
                onClick={() => setDisplayLimit((prev) => prev + 50)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm text-text-secondary hover:text-text hover:bg-gray-50 hover:border-gray-300 transition-all duration-200"
              >
                <ChevronDown className="h-4 w-4" />
                Meer laden ({events.length - displayLimit} overig)
              </button>
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
        <CalendarDays className="h-7 w-7 text-gray-400" />
      </div>
      <h3 className="text-base font-medium text-text mb-1">Nog geen activiteit</h3>
      <p className="text-sm text-text-secondary max-w-sm">
        Maak een nieuwe lead aan om te beginnen. Alle activiteit verschijnt hier in chronologische volgorde.
      </p>
    </div>
  );
}
