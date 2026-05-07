import { useState, useMemo } from 'react';
import { Plus } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { LeadCard } from './LeadCard';
import { LeadMetricsBar } from './LeadMetricsBar';
import { LeadIntakeDialog } from './LeadIntakeDialog';
import { useLeads, useMoveLead } from '@/hooks/useLeads';
import { useLeadColumns } from '@/hooks/useLeadColumns';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import type { Lead, LeadColumn, LeadFilters } from '@/types';

// Static map: Tailwind v4 only sees classes that appear literally in source.
// Building the border class via string interpolation purges it, so we list
// each chip-class explicitly. Keep in sync with COLOR_PRESETS in
// ColumnsManager.tsx.
const COLOR_TO_BORDER: Record<string, string> = {
  'bg-indigo-100 text-indigo-800': 'border-t-indigo-400',
  'bg-blue-100 text-blue-800': 'border-t-blue-400',
  'bg-yellow-100 text-yellow-800': 'border-t-yellow-400',
  'bg-orange-100 text-orange-800': 'border-t-orange-400',
  'bg-purple-100 text-purple-800': 'border-t-purple-400',
  'bg-green-100 text-green-800': 'border-t-green-400',
  'bg-gray-100 text-gray-800': 'border-t-gray-400',
  'bg-pink-100 text-pink-800': 'border-t-pink-400',
  'bg-red-100 text-red-800': 'border-t-red-400',
  'bg-emerald-100 text-emerald-800': 'border-t-emerald-400',
};

function chipToBorder(color: string): string {
  return COLOR_TO_BORDER[color] ?? 'border-t-gray-400';
}

interface LeadKanbanBoardProps {
  searchQuery?: string;
  initiatiefId: string;
  assigneeId?: string;
  tag?: string;
  nextActionFilter?: string;
  stageFilter?: string;
}

export function LeadKanbanBoard({
  searchQuery = '',
  initiatiefId,
  assigneeId,
  tag,
  nextActionFilter,
  stageFilter,
}: LeadKanbanBoardProps) {
  const filters: LeadFilters = {};
  if (initiatiefId) filters.initiatief_id = initiatiefId;
  if (assigneeId) filters.assignee_id = assigneeId;
  if (tag) filters.tag = tag;
  if (nextActionFilter) filters.next_action_filter = nextActionFilter;
  if (stageFilter) filters.stage = stageFilter;

  const { data: leads, isLoading } = useLeads(
    Object.keys(filters).length > 0 ? filters : undefined,
  );
  const { columns, isLoading: columnsLoading } = useLeadColumns(initiatiefId);
  const moveLead = useMoveLead();
  const { openLeadDetail } = useLeadDetail();
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
  const [showIntake, setShowIntake] = useState(false);

  const allLeads = useMemo(() => leads ?? [], [leads]);
  const filteredLeads = useMemo(() => {
    if (!searchQuery) return allLeads;
    const q = searchQuery.toLowerCase();
    return allLeads.filter(
      (l) =>
        l.title.toLowerCase().includes(q) ||
        (l.organization ?? '').toLowerCase().includes(q) ||
        (l.description ?? '').toLowerCase().includes(q) ||
        (l.assignee?.naam ?? '').toLowerCase().includes(q) ||
        l.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [allLeads, searchQuery]);

  const visibleColumns = useMemo<LeadColumn[]>(
    () =>
      [...columns]
        .sort((a, b) => a.sort_order - b.sort_order)
        .filter((c) => !stageFilter || c.slug === stageFilter),
    [columns, stageFilter],
  );

  const leadsByStage = useMemo(() => {
    const map: Record<string, Lead[]> = {};
    for (const col of visibleColumns) {
      map[col.slug] = filteredLeads
        .filter((l) => l.stage === col.slug)
        .sort((a, b) => a.sort_order - b.sort_order);
    }
    return map;
  }, [filteredLeads, visibleColumns]);

  if (isLoading || columnsLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  const handleDragStart = (e: React.DragEvent, lead: Lead) => {
    e.dataTransfer.setData('text/plain', lead.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent, slug: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverColumn(slug);
  };

  const handleDragLeave = () => {
    setDragOverColumn(null);
  };

  const handleDrop = (e: React.DragEvent, targetSlug: string) => {
    e.preventDefault();
    setDragOverColumn(null);
    const leadId = e.dataTransfer.getData('text/plain');
    const lead = allLeads.find((l) => l.id === leadId);
    if (!lead || lead.stage === targetSlug) return;

    moveLead.mutate({ id: leadId, stage: targetSlug });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <LeadMetricsBar />
      </div>

      <div className="-mx-4 px-4 md:mx-0 md:px-0 flex gap-3 min-h-[500px] overflow-x-auto pb-2 snap-x snap-mandatory md:snap-none md:pb-0">
        {visibleColumns.map((col) => (
          <div
            key={col.id}
            onDragOver={(e) => handleDragOver(e, col.slug)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, col.slug)}
            className={`flex-none w-[85vw] sm:w-[320px] md:flex-1 md:min-w-[200px] snap-center ${
              dragOverColumn === col.slug ? 'ring-2 ring-primary-300 ring-inset rounded-xl' : ''
            }`}
          >
            <div
              className={`rounded-xl border border-border bg-gray-50/50 min-h-full flex flex-col border-t-3 ${chipToBorder(col.color)}`}
            >
              <div className="flex items-center justify-between px-3 py-2.5">
                <span
                  className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${col.color}`}
                >
                  {col.name}
                </span>
                <span className="text-xs text-text-secondary tabular-nums">
                  {leadsByStage[col.slug]?.length ?? 0}
                </span>
              </div>

              <div className="flex-1 px-2 pb-2 space-y-2">
                {(leadsByStage[col.slug] ?? []).length > 0 ? (
                  (leadsByStage[col.slug] ?? []).map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={(e) => handleDragStart(e, lead)}
                    >
                      <LeadCard
                        lead={lead}
                        onClick={() => openLeadDetail(lead.id)}
                      />
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-text-secondary text-center py-6">
                    Sleep leads hierheen
                  </p>
                )}
              </div>

              <button
                onClick={() => setShowIntake(true)}
                className="flex items-center justify-center gap-1 px-3 py-2 text-xs text-text-secondary hover:text-text hover:bg-gray-100/80 transition-colors rounded-b-xl"
              >
                <Plus className="h-3.5 w-3.5" />
                Nieuwe lead
              </button>
            </div>
          </div>
        ))}
      </div>

      <LeadIntakeDialog
        open={showIntake}
        onClose={() => setShowIntake(false)}
        defaultInitiatiefId={initiatiefId}
      />
    </div>
  );
}
