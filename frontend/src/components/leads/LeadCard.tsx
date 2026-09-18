import { useCallback, useRef } from 'react';
import { useNlddEvent } from '@/components/nldd/events';
import { isOverdue, formatDateShort } from '@/utils/dates';
import { LeadStage } from '@/types';
import type { Lead } from '@/types';

interface LeadCardProps {
  lead: Lead;
  onClick: () => void;
}

export function LeadCard({ lead, onClick }: LeadCardProps) {
  const ref = useRef<HTMLElement>(null);
  const handleClick = useCallback(() => onClick(), [onClick]);
  useNlddEvent(ref, 'click', handleClick);

  const overdue = lead.next_action_date && isOverdue(lead.next_action_date);
  const isInbox = lead.stage === LeadStage.INBOX;
  const contacts = lead.contact_names ?? [];
  const hasFunnelScores =
    lead.score_strategisch != null &&
    lead.score_politiek != null &&
    lead.score_positie != null;

  return (
    <nldd-card ref={ref} button accessible-label={lead.title} className="block w-full text-left p-3 space-y-1.5">
      <nldd-text size="sm" weight="medium" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
        {lead.title}
      </nldd-text>

      {lead.organization && (
        <nldd-text size="xs" color="secondary" className="truncate block">
          {lead.organisatie_eenheid?.naam ?? lead.organization}
        </nldd-text>
      )}

      {lead.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 overflow-hidden max-h-[3.25rem]">
          {lead.tags.slice(0, 3).map((tag) => (
            <nldd-tag key={tag} text={tag} color="neutral" size="sm" />
          ))}
          {lead.tags.length > 3 && (
            <nldd-text size="xs" color="secondary" className="shrink-0">
              +{lead.tags.length - 3}
            </nldd-text>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 text-xs text-text-secondary">
        {isInbox ? (
          lead.brought_by && (
            <span className="truncate max-w-[120px]">via {lead.brought_by.naam}</span>
          )
        ) : (
          <>
            {lead.assignee && (
              <span className="truncate max-w-[120px]">{lead.assignee.naam}</span>
            )}
            {contacts.length > 0 && (
              <span className="inline-flex items-center gap-0.5" title={contacts.join(', ')}>
                <nldd-icon name="users" size="16" aria-hidden="true" />
                {contacts[0]}
                {contacts.length > 1 && (
                  <span className="text-[10px]">+{contacts.length - 1}</span>
                )}
              </span>
            )}
          </>
        )}

        {lead.next_action_date && (
          <span
            className={`inline-flex items-center gap-0.5 ${
              overdue ? 'text-red-600 font-medium' : ''
            }`}
          >
            <nldd-icon name="calendar" size="16" aria-hidden="true" />
            {formatDateShort(lead.next_action_date)}
          </span>
        )}

        {lead.attachment_count > 0 && (
          <span className="inline-flex items-center gap-0.5 ml-auto">
            <nldd-icon name="paperclip" size="16" aria-hidden="true" />
            {lead.attachment_count}
          </span>
        )}

        {hasFunnelScores && (
          <span
            className={`tabular-nums text-[10px] text-text-secondary ${lead.attachment_count > 0 ? '' : 'ml-auto'}`}
            title={`Strategisch ${lead.score_strategisch} · Politiek ${lead.score_politiek} · Positie ${lead.score_positie}`}
          >
            {lead.score_strategisch}·{lead.score_politiek}·{lead.score_positie}
          </span>
        )}
      </div>
    </nldd-card>
  );
}
