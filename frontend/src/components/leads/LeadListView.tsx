import { useMemo, useState } from 'react';
import { Calendar } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { useLeads, useMergeLeads, useDeleteLead } from '@/hooks/useLeads';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { LeadMetricsBar } from './LeadMetricsBar';
import {
  LeadStage,
  LEAD_STAGE_ORDER,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
} from '@/types';
import type { Lead, LeadFilters } from '@/types';
import { isOverdue, formatDateShort, timeAgo } from '@/utils/dates';

const SORT_OPTIONS: SelectOption[] = [
  { value: '', label: 'Standaard' },
  { value: 'created_at', label: 'Aangemaakt' },
  { value: 'updated_at', label: 'Laatst gewijzigd' },
  { value: 'next_action_date', label: 'Volgende actie' },
];

interface LeadListViewProps {
  searchQuery?: string;
  initiatiefId: string;
  assigneeId?: string;
  tag?: string;
  nextActionFilter?: string;
  stageFilter?: string;
}

export function LeadListView({
  searchQuery = '',
  initiatiefId,
  assigneeId,
  tag,
  nextActionFilter,
  stageFilter,
}: LeadListViewProps) {
  const [sortBy, setSortBy] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showMergeDialog, setShowMergeDialog] = useState(false);

  const filters: LeadFilters = {};
  if (initiatiefId) filters.initiatief_id = initiatiefId;
  if (assigneeId) filters.assignee_id = assigneeId;
  if (tag) filters.tag = tag;
  if (nextActionFilter) filters.next_action_filter = nextActionFilter;
  if (stageFilter) filters.stage = stageFilter;
  if (sortBy) filters.sort_by = sortBy;

  const { data: leads, isLoading } = useLeads(
    Object.keys(filters).length > 0 ? filters : undefined,
  );
  const { openLeadDetail } = useLeadDetail();
  const mergeMutation = useMergeLeads();
  const deleteLead = useDeleteLead();

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allLeads = leads ?? [];

  const stageIndex = useMemo(() => {
    const map = new Map<string, number>();
    LEAD_STAGE_ORDER.forEach((s, i) => map.set(s, i));
    return map;
  }, []);

  const filteredLeads = useMemo(() => {
    if (!leads) return [];
    if (!searchQuery) return leads;
    const q = searchQuery.toLowerCase();
    return leads.filter((l) =>
      l.title.toLowerCase().includes(q) ||
      (l.organization ?? '').toLowerCase().includes(q) ||
      (l.description ?? '').toLowerCase().includes(q) ||
      (l.assignee?.naam ?? '').toLowerCase().includes(q) ||
      l.tags.some((t) => t.toLowerCase().includes(q))
    );
  }, [leads, searchQuery]);

  const sortedLeads = useMemo(() => {
    return [...filteredLeads].sort((a, b) => {
      const sa = stageIndex.get(a.stage) ?? 99;
      const sb = stageIndex.get(b.stage) ?? 99;
      if (sa !== sb) return sa - sb;
      return a.sort_order - b.sort_order;
    });
  }, [filteredLeads, stageIndex]);

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <LeadMetricsBar />
        <div className="w-full sm:w-44">
          <CreatableSelect
            value={sortBy}
            onChange={setSortBy}
            options={SORT_OPTIONS}
            placeholder="Standaard"
            searchable={false}
            onClear={sortBy ? () => setSortBy('') : undefined}
          />
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2">
          <span className="text-sm font-medium text-amber-800">
            {selectedIds.size} lead{selectedIds.size !== 1 ? 's' : ''} geselecteerd
          </span>
          {selectedIds.size === 2 && (
            <Button size="sm" onClick={() => setShowMergeDialog(true)}>
              Samenvoegen
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
            onClick={async () => {
              if (!confirm(`${selectedIds.size} lead${selectedIds.size !== 1 ? 's' : ''} verwijderen?`)) return;
              for (const id of selectedIds) {
                await deleteLead.mutateAsync(id);
              }
              setSelectedIds(new Set());
            }}
          >
            Verwijderen
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
            Deselecteren
          </Button>
        </div>
      )}

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
                  <th className="w-10 px-4 py-3">
                    <span className="sr-only">Selecteer</span>
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Titel
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Organisatie
                  </th>
                  <th className="text-left px-4 py-3 font-medium text-text-secondary">
                    Initiatief
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
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedIds.has(lead.id)}
                          onChange={() => toggleSelect(lead.id)}
                          className="rounded border-border text-primary-600 focus:ring-primary-400"
                        />
                      </td>
                      <td className="px-4 py-3 font-medium text-text max-w-[260px] truncate">
                        {lead.title}
                      </td>
                      <td className="px-4 py-3 text-text-secondary truncate max-w-[180px]">
                        {lead.externe_organisatie?.naam ??
                          lead.organization ??
                          '-'}
                      </td>
                      <td className="px-4 py-3">
                        {lead.initiatief ? (
                          <span
                            className="inline-block rounded-full px-2 py-0.5 text-[10px] font-medium text-white whitespace-nowrap"
                            style={{ backgroundColor: lead.initiatief.kleur || '#6B7280' }}
                          >
                            {lead.initiatief.naam}
                          </span>
                        ) : (
                          <span className="text-text-secondary">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${LEAD_STAGE_COLORS[lead.stage]}`}
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
                        <span title={formatDateShort(lead.created_at)}>{timeAgo(lead.created_at)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showMergeDialog && (
        <Modal
          open={showMergeDialog}
          onClose={() => setShowMergeDialog(false)}
          title="Leads samenvoegen"
          size="md"
        >
          <div className="space-y-4">
            <p className="text-sm text-text-secondary">
              Kies de lead die je wilt behouden. De andere lead wordt hierin samengevoegd
              (activiteiten, contacten, tags en bijlagen worden overgenomen).
            </p>
            {Array.from(selectedIds).map((id) => {
              const lead = allLeads.find((l) => l.id === id);
              if (!lead) return null;
              return (
                <button
                  key={id}
                  onClick={async () => {
                    const otherId = Array.from(selectedIds).find((x) => x !== id)!;
                    await mergeMutation.mutateAsync({ sourceId: otherId, targetId: id });
                    setShowMergeDialog(false);
                    setSelectedIds(new Set());
                  }}
                  disabled={mergeMutation.isPending}
                  className="w-full text-left p-4 rounded-lg border border-border hover:border-primary-400 hover:bg-primary-50/50 transition-colors disabled:opacity-50"
                >
                  <div className="font-medium">{lead.title}</div>
                  <div className="text-sm text-text-secondary">
                    {lead.organization ?? 'geen organisatie'} -{' '}
                    {LEAD_STAGE_LABELS[lead.stage as LeadStage]}
                  </div>
                  <div className="text-xs text-primary-600 mt-1">
                    ← Deze behouden
                  </div>
                </button>
              );
            })}
          </div>
        </Modal>
      )}
    </div>
  );
}
