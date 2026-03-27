import { useMemo, useState } from 'react';
import { Calendar } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useLeads } from '@/hooks/useLeads';
import { usePeople } from '@/hooks/usePeople';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { LeadMetricsBar } from './LeadMetricsBar';
import {
  LEAD_STAGE_ORDER,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
} from '@/types';
import type { Lead, LeadFilters } from '@/types';
import { isOverdue, formatDateShort } from '@/utils/dates';

export function LeadListView() {
  const [filterAssignee, setFilterAssignee] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [nextActionFilter, setNextActionFilter] = useState('');
  const [sortBy, setSortBy] = useState('');

  const filters: LeadFilters = {};
  if (filterAssignee) filters.assignee_id = filterAssignee;
  if (filterTag) filters.tag = filterTag;
  if (nextActionFilter) filters.next_action_filter = nextActionFilter;
  if (sortBy) filters.sort_by = sortBy;

  const { data: leads, isLoading } = useLeads(
    Object.keys(filters).length > 0 ? filters : undefined,
  );
  const { data: people } = usePeople();
  const { currentPerson } = useCurrentPerson();
  const { openLeadDetail } = useLeadDetail();

  const stageIndex = useMemo(() => {
    const map = new Map<string, number>();
    LEAD_STAGE_ORDER.forEach((s, i) => map.set(s, i));
    return map;
  }, []);

  const sortedLeads = useMemo(() => {
    if (!leads) return [];
    return [...leads].sort((a, b) => {
      const sa = stageIndex.get(a.stage) ?? 99;
      const sb = stageIndex.get(b.stage) ?? 99;
      if (sa !== sb) return sa - sb;
      return a.sort_order - b.sort_order;
    });
  }, [leads, stageIndex]);

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <LeadMetricsBar />
      </div>

      <div className="flex items-center gap-3 mb-4">
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
        <input
          type="text"
          value={filterTag}
          onChange={(e) => setFilterTag(e.target.value)}
          placeholder="Filter op tag..."
          className="rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:border-primary-400 w-48"
        />
        <select
          value={nextActionFilter}
          onChange={(e) => setNextActionFilter(e.target.value)}
          className="rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:border-primary-400"
        >
          <option value="">Alle acties</option>
          <option value="overdue">Achterstallig</option>
          <option value="today">Vandaag</option>
          <option value="this_week">Deze week</option>
        </select>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:border-primary-400"
        >
          <option value="">Standaard</option>
          <option value="created_at">Aangemaakt</option>
          <option value="updated_at">Laatst gewijzigd</option>
          <option value="next_action_date">Volgende actie</option>
        </select>
        {(filterAssignee || filterTag || nextActionFilter || sortBy) && (
          <button
            onClick={() => {
              setFilterAssignee('');
              setFilterTag('');
              setNextActionFilter('');
              setSortBy('');
            }}
            className="text-sm text-text-secondary hover:text-text transition-colors"
          >
            Filters wissen
          </button>
        )}
      </div>

      {sortedLeads.length === 0 ? (
        <EmptyState
          title="Geen leads gevonden"
          description="Er zijn nog geen leads, of de huidige filters geven geen resultaten."
        />
      ) : (
        <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-gray-50/50">
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Titel
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Organisatie
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Fase
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Verantwoordelijke
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Volgende actie
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Tags
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Aangemaakt
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedLeads.map((lead: Lead) => {
                  const overdue =
                    lead.next_action_date && isOverdue(lead.next_action_date);
                  return (
                    <tr
                      key={lead.id}
                      onClick={() => openLeadDetail(lead.id)}
                      className="border-b border-border last:border-b-0 hover:bg-gray-50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 font-medium text-text max-w-[260px] truncate">
                        {lead.title}
                      </td>
                      <td className="px-4 py-3 text-text-secondary truncate max-w-[180px]">
                        {lead.externe_organisatie?.naam ??
                          lead.organization ??
                          '-'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${LEAD_STAGE_COLORS[lead.stage]}`}
                        >
                          {LEAD_STAGE_LABELS[lead.stage]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text-secondary truncate max-w-[150px]">
                        {lead.assignee?.naam ?? '-'}
                      </td>
                      <td className="px-4 py-3">
                        {lead.next_action_date ? (
                          <span
                            className={`inline-flex items-center gap-1 text-xs ${
                              overdue
                                ? 'text-red-600 font-medium'
                                : 'text-text-secondary'
                            }`}
                          >
                            <Calendar className="h-3 w-3" />
                            {formatDateShort(lead.next_action_date)}
                          </span>
                        ) : (
                          <span className="text-text-secondary">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {lead.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="inline-block rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-text-secondary"
                            >
                              {tag}
                            </span>
                          ))}
                          {lead.tags.length > 3 && (
                            <span className="text-[10px] text-text-secondary">
                              +{lead.tags.length - 3}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-text-secondary whitespace-nowrap">
                        {formatDateShort(lead.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
