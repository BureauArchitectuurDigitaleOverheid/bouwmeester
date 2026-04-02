import { useMemo, useState, useEffect, useRef } from 'react';
import { Inbox, UserPlus, Snowflake, ChevronDown } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useLeads, useUpdateLead, useMoveLead } from '@/hooks/useLeads';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { usePeople } from '@/hooks/usePeople';
import { LeadStage } from '@/types';
import type { Lead, LeadFilters } from '@/types';
import { timeAgo } from '@/utils/dates';

interface LeadInboxViewProps {
  searchQuery?: string;
  initiatiefId: string;
}

type DateGroup = 'vandaag' | 'gisteren' | 'deze_week' | 'ouder';

const DATE_GROUP_LABELS: Record<DateGroup, string> = {
  vandaag: 'Vandaag',
  gisteren: 'Gisteren',
  deze_week: 'Deze week',
  ouder: 'Ouder',
};

function getDateGroup(dateStr: string): DateGroup {
  const date = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);

  if (date >= today) return 'vandaag';
  if (date >= yesterday) return 'gisteren';
  if (date >= weekAgo) return 'deze_week';
  return 'ouder';
}

export function LeadInboxView({
  searchQuery = '',
  initiatiefId,
}: LeadInboxViewProps) {
  const filters: LeadFilters = { stage: LeadStage.INBOX };
  if (initiatiefId) filters.initiatief_id = initiatiefId;

  const { data: leads, isLoading } = useLeads(filters);
  const { data: people } = usePeople();
  const { openLeadDetail } = useLeadDetail();
  const { currentPerson } = useCurrentPerson();
  const updateLead = useUpdateLead();
  const moveLead = useMoveLead();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [assignDropdownId, setAssignDropdownId] = useState<string | null>(null);
  const assignDropdownRef = useRef<HTMLDivElement>(null);

  // Close assign dropdown on click outside
  useEffect(() => {
    if (!assignDropdownId) return;
    const handleClick = (e: MouseEvent) => {
      if (assignDropdownRef.current && !assignDropdownRef.current.contains(e.target as Node)) {
        setAssignDropdownId(null);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [assignDropdownId]);

  const filteredLeads = useMemo(() => {
    if (!leads) return [];
    if (!searchQuery) return leads;
    const q = searchQuery.toLowerCase();
    return leads.filter(
      (l) =>
        l.title.toLowerCase().includes(q) ||
        (l.organization ?? '').toLowerCase().includes(q) ||
        (l.description ?? '').toLowerCase().includes(q) ||
        (l.brought_by?.naam ?? '').toLowerCase().includes(q) ||
        l.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [leads, searchQuery]);

  const grouped = useMemo(() => {
    const groups: Record<DateGroup, Lead[]> = {
      vandaag: [],
      gisteren: [],
      deze_week: [],
      ouder: [],
    };
    for (const lead of filteredLeads) {
      groups[getDateGroup(lead.created_at)].push(lead);
    }
    return groups;
  }, [filteredLeads]);

  const handleClaim = (lead: Lead) => {
    if (!currentPerson) return;
    updateLead.mutate(
      { id: lead.id, data: { assignee_id: currentPerson.id, stage: LeadStage.VERKENNEN } },
    );
  };

  const handleAssign = (leadId: string, personId: string) => {
    updateLead.mutate(
      { id: leadId, data: { assignee_id: personId, stage: LeadStage.VERKENNEN } },
      { onSuccess: () => setAssignDropdownId(null) },
    );
  };

  const handleKoelkast = (leadId: string) => {
    moveLead.mutate({ id: leadId, stage: LeadStage.KOELKAST });
  };

  const handleBatchClaim = async () => {
    if (!currentPerson) return;
    const ids = [...selectedIds];
    try {
      await Promise.all(
        ids.map((id) =>
          updateLead.mutateAsync(
            { id, data: { assignee_id: currentPerson.id, stage: LeadStage.VERKENNEN } },
          ),
        ),
      );
      setSelectedIds(new Set());
    } catch {
      // Keep failed items selected so user can retry
      setSelectedIds(new Set(ids));
    }
  };

  const handleBatchKoelkast = async () => {
    const ids = [...selectedIds];
    try {
      await Promise.all(
        ids.map((id) => moveLead.mutateAsync({ id, stage: LeadStage.KOELKAST })),
      );
      setSelectedIds(new Set());
    } catch {
      setSelectedIds(new Set(ids));
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredLeads.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredLeads.map((l) => l.id)));
    }
  };

  const personOptions = useMemo(
    () =>
      (people ?? [])
        .filter((p) => p.is_active && p.id !== currentPerson?.id)
        .sort((a, b) => a.naam.localeCompare(b.naam))
        .map((p) => ({ value: p.id, label: p.naam })),
    [people, currentPerson],
  );

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  if (filteredLeads.length === 0) {
    return (
      <EmptyState
        icon={<Inbox className="h-10 w-10" />}
        title="Geen nieuwe leads"
        description="Alles is opgepakt! Nieuwe leads verschijnen hier automatisch."
      />
    );
  }

  const groupOrder: DateGroup[] = ['vandaag', 'gisteren', 'deze_week', 'ouder'];

  return (
    <div className="space-y-2">
      {/* Batch action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-xl bg-primary-50 border border-primary-200 px-4 py-2.5">
          <span className="text-sm font-medium text-primary-700">
            {selectedIds.size} geselecteerd
          </span>
          <Button size="sm" onClick={handleBatchClaim} disabled={!currentPerson}>
            Oppakken
          </Button>
          <Button size="sm" variant="secondary" onClick={handleBatchKoelkast}>
            Koelkast
          </Button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="ml-auto text-sm text-text-secondary hover:text-text"
          >
            Deselecteren
          </button>
        </div>
      )}

      {/* Select all */}
      {filteredLeads.length > 1 && selectedIds.size === 0 && (
        <div className="px-3">
          <button
            onClick={toggleSelectAll}
            className="text-xs text-text-secondary hover:text-text transition-colors"
          >
            Alles selecteren ({filteredLeads.length})
          </button>
        </div>
      )}

      {groupOrder.map((group) => {
        const items = grouped[group];
        if (items.length === 0) return null;

        return (
          <div key={group}>
            <div className="px-3 py-1.5">
              <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                {DATE_GROUP_LABELS[group]}
              </span>
            </div>

            <div className="space-y-1">
              {items.map((lead) => (
                <div
                  key={lead.id}
                  className="group flex items-center gap-3 rounded-xl border border-border bg-white px-4 py-3 hover:border-primary-200 hover:shadow-sm transition-all"
                >
                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={selectedIds.has(lead.id)}
                    onChange={() => toggleSelect(lead.id)}
                    className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 shrink-0"
                  />

                  {/* Main content - clickable */}
                  <button
                    onClick={() => openLeadDetail(lead.id)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text truncate">
                        {lead.title}
                      </span>
                      {lead.tags.length > 0 && (
                        <div className="hidden sm:flex gap-1 shrink-0">
                          {lead.tags.slice(0, 2).map((tag) => (
                            <span
                              key={tag}
                              className="inline-block rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-text-secondary"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 text-xs text-text-secondary">
                      {lead.brought_by && (
                        <span>via {lead.brought_by.naam}</span>
                      )}
                      {lead.organization && (
                        <span className="truncate">
                          {lead.externe_organisatie?.naam ?? lead.organization}
                        </span>
                      )}
                      <span>{timeAgo(lead.created_at)}</span>
                    </div>
                  </button>

                  {/* Actions - visible on hover and focus-within */}
                  <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity shrink-0">
                    <Button
                      size="sm"
                      onClick={() => handleClaim(lead)}
                      disabled={!currentPerson}
                      title="Zelf oppakken"
                    >
                      Oppakken
                    </Button>

                    <div className="relative" ref={assignDropdownId === lead.id ? assignDropdownRef : undefined}>
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<UserPlus className="h-3.5 w-3.5" />}
                        onClick={() =>
                          setAssignDropdownId(
                            assignDropdownId === lead.id ? null : lead.id,
                          )
                        }
                        title="Toewijzen aan iemand anders"
                      >
                        <ChevronDown className="h-3 w-3" />
                      </Button>

                      {assignDropdownId === lead.id && (
                        <div className="absolute right-0 top-full mt-1 z-20 w-56">
                          <CreatableSelect
                            value=""
                            onChange={(personId) => handleAssign(lead.id, personId)}
                            options={personOptions}
                            placeholder="Zoek een persoon..."
                          />
                        </div>
                      )}
                    </div>

                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<Snowflake className="h-3.5 w-3.5" />}
                      onClick={() => handleKoelkast(lead.id)}
                      title="Naar koelkast"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
