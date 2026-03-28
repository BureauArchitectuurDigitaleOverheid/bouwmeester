import { useState } from 'react';
import { Plus } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { LeadCard } from './LeadCard';
import { LeadMetricsBar } from './LeadMetricsBar';
import { LeadIntakeDialog } from './LeadIntakeDialog';
import { useLeads, useMoveLead } from '@/hooks/useLeads';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import {
  LeadStage,
  LEAD_STAGE_ORDER,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
} from '@/types';
import type { Lead, LeadFilters } from '@/types';

const COLUMN_BORDER_COLORS: Record<LeadStage, string> = {
  [LeadStage.VERKENNEN]: 'border-t-blue-400',
  [LeadStage.EERSTE_GESPREK]: 'border-t-yellow-400',
  [LeadStage.INTERNE_CHECK]: 'border-t-orange-400',
  [LeadStage.FOLLOW_UP]: 'border-t-purple-400',
  [LeadStage.IN_THE_POCKET]: 'border-t-green-400',
  [LeadStage.KOELKAST]: 'border-t-gray-400',
};

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
  const moveLead = useMoveLead();
  const { openLeadDetail } = useLeadDetail();
  const [dragOverColumn, setDragOverColumn] = useState<LeadStage | null>(null);
  const [showIntake, setShowIntake] = useState(false);

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  const allLeads = leads ?? [];

  const filteredLeads = searchQuery
    ? allLeads.filter((l) => {
        const q = searchQuery.toLowerCase();
        return (
          l.title.toLowerCase().includes(q) ||
          (l.organization ?? '').toLowerCase().includes(q) ||
          (l.description ?? '').toLowerCase().includes(q) ||
          (l.assignee?.naam ?? '').toLowerCase().includes(q) ||
          l.tags.some((t) => t.toLowerCase().includes(q))
        );
      })
    : allLeads;

  const leadsByStage = LEAD_STAGE_ORDER.reduce(
    (acc, stage) => {
      acc[stage] = filteredLeads
        .filter((l) => l.stage === stage)
        .sort((a, b) => a.sort_order - b.sort_order);
      return acc;
    },
    {} as Record<LeadStage, Lead[]>,
  );

  const handleDragStart = (e: React.DragEvent, lead: Lead) => {
    e.dataTransfer.setData('text/plain', lead.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent, stage: LeadStage) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverColumn(stage);
  };

  const handleDragLeave = () => {
    setDragOverColumn(null);
  };

  const handleDrop = (e: React.DragEvent, targetStage: LeadStage) => {
    e.preventDefault();
    setDragOverColumn(null);
    const leadId = e.dataTransfer.getData('text/plain');
    const lead = allLeads.find((l) => l.id === leadId);
    if (!lead || lead.stage === targetStage) return;

    moveLead.mutate({ id: leadId, stage: targetStage });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <LeadMetricsBar />
      </div>

      <div className="-mx-4 px-4 md:mx-0 md:px-0 flex gap-3 min-h-[500px] overflow-x-auto pb-2 snap-x snap-mandatory md:snap-none md:pb-0">
        {LEAD_STAGE_ORDER.filter((s) => !stageFilter || s === stageFilter).map((stage) => (
          <div
            key={stage}
            onDragOver={(e) => handleDragOver(e, stage)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, stage)}
            className={`flex-none w-[85vw] sm:w-[320px] md:flex-1 md:min-w-[200px] snap-center ${
              dragOverColumn === stage ? 'ring-2 ring-primary-300 ring-inset rounded-xl' : ''
            }`}
          >
            <div
              className={`rounded-xl border border-border bg-gray-50/50 min-h-full flex flex-col border-t-3 ${COLUMN_BORDER_COLORS[stage]}`}
            >
              {/* Column header */}
              <div className="flex items-center justify-between px-3 py-2.5">
                <span
                  className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${LEAD_STAGE_COLORS[stage]}`}
                >
                  {LEAD_STAGE_LABELS[stage]}
                </span>
                <span className="text-xs text-text-secondary tabular-nums">
                  {leadsByStage[stage]?.length ?? 0}
                </span>
              </div>

              {/* Cards */}
              <div className="flex-1 px-2 pb-2 space-y-2">
                {(leadsByStage[stage] ?? []).length > 0 ? (
                  (leadsByStage[stage] ?? []).map((lead) => (
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

              {/* Add lead button */}
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

      <LeadIntakeDialog open={showIntake} onClose={() => setShowIntake(false)} defaultInitiatiefId={initiatiefId} />
    </div>
  );
}
