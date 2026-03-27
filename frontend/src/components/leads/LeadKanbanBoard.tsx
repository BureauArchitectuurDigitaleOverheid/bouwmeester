import { useState } from 'react';
import { Plus } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { LeadCard } from './LeadCard';
import { LeadMetricsBar } from './LeadMetricsBar';
import { LeadIntakeDialog } from './LeadIntakeDialog';
import { useLeads, useMoveLead } from '@/hooks/useLeads';
import { usePeople } from '@/hooks/usePeople';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
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

export function LeadKanbanBoard() {
  const [filterAssignee, setFilterAssignee] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [nextActionFilter, setNextActionFilter] = useState('');

  const filters: LeadFilters = {};
  if (filterAssignee) filters.assignee_id = filterAssignee;
  if (filterTag) filters.tag = filterTag;
  if (nextActionFilter) filters.next_action_filter = nextActionFilter;

  const { data: leads, isLoading } = useLeads(
    Object.keys(filters).length > 0 ? filters : undefined,
  );
  const moveLead = useMoveLead();
  const { openLeadDetail } = useLeadDetail();
  const { data: people } = usePeople();
  const { currentPerson } = useCurrentPerson();
  const [dragOverColumn, setDragOverColumn] = useState<LeadStage | null>(null);
  const [showIntake, setShowIntake] = useState(false);

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  const allLeads = leads ?? [];

  const leadsByStage = LEAD_STAGE_ORDER.reduce(
    (acc, stage) => {
      acc[stage] = allLeads
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
        {(filterAssignee || filterTag || nextActionFilter) && (
          <button
            onClick={() => {
              setFilterAssignee('');
              setFilterTag('');
              setNextActionFilter('');
            }}
            className="text-sm text-text-secondary hover:text-text transition-colors"
          >
            Filters wissen
          </button>
        )}
      </div>

      <div className="-mx-4 px-4 md:mx-0 md:px-0 flex gap-3 min-h-[500px] overflow-x-auto pb-2 snap-x snap-mandatory md:snap-none md:pb-0">
        {LEAD_STAGE_ORDER.map((stage) => (
          <div
            key={stage}
            onDragOver={(e) => handleDragOver(e, stage)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, stage)}
            className={`rounded-xl border border-border bg-gray-50/50 border-t-4 w-[280px] min-w-[280px] shrink-0 flex flex-col ${COLUMN_BORDER_COLORS[stage]} transition-colors ${
              dragOverColumn === stage ? 'bg-primary-50/50 border-primary-200' : ''
            }`}
          >
            <div className="px-3 py-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text flex items-center gap-2">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${LEAD_STAGE_COLORS[stage]}`}
                >
                  {LEAD_STAGE_LABELS[stage]}
                </span>
              </h3>
              <span className="text-xs text-text-secondary bg-white rounded-full px-2 py-0.5 border border-border">
                {leadsByStage[stage]?.length ?? 0}
              </span>
            </div>

            <div className="px-2 pb-2 space-y-2 flex-1 overflow-y-auto min-h-[100px]">
              {leadsByStage[stage]?.map((lead) => (
                <div
                  key={lead.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, lead)}
                  className="cursor-grab active:cursor-grabbing"
                >
                  <LeadCard
                    lead={lead}
                    onClick={() => openLeadDetail(lead.id)}
                  />
                </div>
              ))}

              {(leadsByStage[stage]?.length ?? 0) === 0 && (
                <div className="flex items-center justify-center h-[80px] text-xs text-text-secondary">
                  Sleep leads hierheen
                </div>
              )}
            </div>

            <div className="px-2 pb-2">
              <button
                onClick={() => setShowIntake(true)}
                className="w-full flex items-center justify-center gap-1 py-1.5 text-xs text-text-secondary hover:text-text hover:bg-gray-100 rounded-lg transition-colors"
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
      />
    </div>
  );
}
