import { useMemo, useState, useRef, useCallback } from 'react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { NlddButton } from '@/components/nldd/NlddLink';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { orUndef, useNlddEvent, useNlddOverlay } from '@/components/nldd/events';
import { useLeads, useUpdateLead, useMoveLead } from '@/hooks/useLeads';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { usePeople } from '@/hooks/usePeople';
import { LeadStage } from '@/types';
import type { Lead, LeadFilters } from '@/types';
import { timeAgo, formatDateShort } from '@/utils/dates';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';

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
    const results = await Promise.allSettled(
      ids.map((id) =>
        updateLead.mutateAsync(
          { id, data: { assignee_id: currentPerson.id, stage: LeadStage.VERKENNEN } },
        ),
      ),
    );
    const failedIds = ids.filter((_, i) => results[i].status === 'rejected');
    setSelectedIds(new Set(failedIds));
  };

  const handleBatchKoelkast = async () => {
    const ids = [...selectedIds];
    const results = await Promise.allSettled(
      ids.map((id) => moveLead.mutateAsync({ id, stage: LeadStage.KOELKAST })),
    );
    const failedIds = ids.filter((_, i) => results[i].status === 'rejected');
    setSelectedIds(new Set(failedIds));
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
        icon="inbox"
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
          <nldd-text size="sm" weight="medium" color="accent">
            {selectedIds.size} geselecteerd
          </nldd-text>
          <NlddButton
            size="sm"
            text="Oppakken"
            onClick={handleBatchClaim}
            disabled={!currentPerson}
          />
          <NlddButton
            size="sm"
            variant="secondary"
            text="Koelkast"
            onClick={handleBatchKoelkast}
          />
          <NlddButton
            size="sm"
            variant="neutral-transparent"
            text="Deselecteren"
            onClick={() => setSelectedIds(new Set())}
            className="ml-auto"
          />
        </div>
      )}

      {/* Select all */}
      {filteredLeads.length > 1 && selectedIds.size === 0 && (
        <div className="px-3">
          <NlddButton
            size="xs"
            variant="neutral-transparent"
            text={`Alles selecteren (${filteredLeads.length})`}
            onClick={toggleSelectAll}
          />
        </div>
      )}

      {groupOrder.map((group) => {
        const items = grouped[group];
        if (items.length === 0) return null;

        return (
          <div key={group}>
            <div className="px-3 py-1.5">
              <nldd-text size="xs" weight="medium" color="secondary" className="uppercase tracking-wider">
                {DATE_GROUP_LABELS[group]}
              </nldd-text>
            </div>

            <nldd-list variant="simple" dividers="always" accessible-label={`Leads: ${DATE_GROUP_LABELS[group]}`}>
              {items.map((lead) => (
                <LeadInboxRow
                  key={lead.id}
                  lead={lead}
                  selected={selectedIds.has(lead.id)}
                  onToggleSelect={() => toggleSelect(lead.id)}
                  onOpen={() => openLeadDetail(lead.id)}
                  onClaim={() => handleClaim(lead)}
                  canClaim={!!currentPerson}
                  assignOpen={assignDropdownId === lead.id}
                  onToggleAssign={() =>
                    setAssignDropdownId(assignDropdownId === lead.id ? null : lead.id)
                  }
                  onAssign={(personId) => handleAssign(lead.id, personId)}
                  personOptions={personOptions}
                  onKoelkast={() => handleKoelkast(lead.id)}
                />
              ))}
            </nldd-list>
          </div>
        );
      })}
    </div>
  );
}

interface LeadInboxRowProps {
  lead: Lead;
  selected: boolean;
  onToggleSelect: () => void;
  onOpen: () => void;
  onClaim: () => void;
  canClaim: boolean;
  assignOpen: boolean;
  onToggleAssign: () => void;
  onAssign: (personId: string) => void;
  personOptions: { value: string; label: string }[];
  onKoelkast: () => void;
}

/**
 * One inbox row: a checkbox segment, the clickable lead summary, and three
 * action segments. `nldd-list-item` only supports one control type at a time
 * (button/checkbox/href), so a row needing several lives entirely in segments
 * — the item itself carries none of the three.
 */
function LeadInboxRow({
  lead,
  selected,
  onToggleSelect,
  onOpen,
  onClaim,
  canClaim,
  assignOpen,
  onToggleAssign,
  onAssign,
  personOptions,
  onKoelkast,
}: LeadInboxRowProps) {
  const checkboxRef = useRef<HTMLElement>(null);
  const openRef = useRef<HTMLElement>(null);
  const claimRef = useRef<HTMLElement>(null);
  const assignTriggerRef = useRef<HTMLElement>(null);
  const koelkastRef = useRef<HTMLElement>(null);
  const popoverRef = useRef<HTMLElement & { show?: () => void; hide?: () => void }>(null);

  useNlddEvent(checkboxRef, 'change', onToggleSelect);
  useNlddEvent(openRef, 'click', onOpen);
  useNlddEvent(claimRef, 'click', useCallback(() => onClaim(), [onClaim]));
  useNlddEvent(assignTriggerRef, 'click', onToggleAssign);
  useNlddEvent(koelkastRef, 'click', useCallback(() => onKoelkast(), [onKoelkast]));
  useNlddOverlay(popoverRef, assignOpen);

  return (
    <nldd-list-item>
      <nldd-list-item-segment ref={checkboxRef} checkbox checked={orUndef(selected)} accessible-label={`Selecteer ${lead.title}`} />

      <nldd-list-item-segment ref={openRef} button width="full" accessible-label={lead.title}>
        <div className="text-left">
          <span className="text-sm font-medium text-text truncate block w-full">{lead.title}</span>

          {lead.description && (
            <div className="text-xs text-text-secondary mt-1 line-clamp-2 break-words [&_p]:m-0 [&_p]:leading-snug">
              <RichTextDisplay content={lead.description} fallback="" />
            </div>
          )}

          <div className="flex items-center gap-x-3 gap-y-1 flex-wrap mt-1 text-xs text-text-secondary">
            {lead.brought_by && (
              <span className="truncate max-w-[160px]">via {lead.brought_by.naam}</span>
            )}
            {lead.organization && (
              <span className="truncate max-w-[160px]">
                {lead.organisatie_eenheid?.naam ?? lead.organization}
              </span>
            )}
            {lead.contact_names.length > 0 && (
              <span className="inline-flex items-center gap-0.5 truncate max-w-[160px]" title={lead.contact_names.join(', ')}>
                <nldd-icon name="users" size="16" aria-hidden="true" />
                <span className="truncate">{lead.contact_names[0]}</span>
                {lead.contact_names.length > 1 && (
                  <span className="shrink-0">+{lead.contact_names.length - 1}</span>
                )}
              </span>
            )}
            {lead.next_action_date && (
              <span className="inline-flex items-center gap-0.5">
                <nldd-icon name="calendar" size="16" aria-hidden="true" />
                {formatDateShort(lead.next_action_date)}
              </span>
            )}
            {lead.attachment_count > 0 && (
              <span className="inline-flex items-center gap-0.5">
                <nldd-icon name="paperclip" size="16" aria-hidden="true" />
                {lead.attachment_count}
              </span>
            )}
            <span>{timeAgo(lead.created_at)}</span>
          </div>

          {lead.tags.length > 0 && (
            <div className="flex gap-1 flex-wrap mt-1">
              {lead.tags.slice(0, 4).map((tag) => (
                <nldd-tag key={tag} text={tag} color="neutral" size="sm" />
              ))}
              {lead.tags.length > 4 && (
                <nldd-text size="xs" color="secondary">+{lead.tags.length - 4}</nldd-text>
              )}
            </div>
          )}
        </div>
      </nldd-list-item-segment>

      <nldd-list-item-segment ref={claimRef} button disabled={orUndef(!canClaim)} accessible-label="Zelf oppakken">
        Oppakken
      </nldd-list-item-segment>

      <nldd-list-item-segment
        ref={assignTriggerRef}
        button
        id={`assign-trigger-${lead.id}`}
        accessible-label="Toewijzen aan iemand anders"
      >
        <nldd-icon name="person-badge-plus" size="16" aria-hidden="true" />
        <nldd-icon name="chevron-down" size="16" aria-hidden="true" />
      </nldd-list-item-segment>
      {/* Popovers render at the document root: this one sits after the row
          rather than nested in it, anchored by id so it never gets sized by
          the row's own layout. */}
      <nldd-popover
        ref={popoverRef}
        anchor={`assign-trigger-${lead.id}`}
        accessible-label="Toewijzen aan iemand anders"
        width="280px"
      >
        <CreatableSelect
          value=""
          onChange={onAssign}
          options={personOptions}
          placeholder="Zoek een persoon..."
        />
      </nldd-popover>

      <nldd-list-item-segment ref={koelkastRef} button accessible-label="Naar koelkast">
        <nldd-icon name="snowflake" size="16" aria-hidden="true" />
      </nldd-list-item-segment>
    </nldd-list-item>
  );
}
