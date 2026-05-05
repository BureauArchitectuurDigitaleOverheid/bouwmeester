import { Paperclip, Calendar, Users } from 'lucide-react';
import { isOverdue, formatDateShort } from '@/utils/dates';
import { LeadStage } from '@/types';
import type { Lead } from '@/types';

interface LeadCardProps {
  lead: Lead;
  onClick: () => void;
}

export function LeadCard({ lead, onClick }: LeadCardProps) {
  const overdue = lead.next_action_date && isOverdue(lead.next_action_date);
  const isInbox = lead.stage === LeadStage.INBOX;
  const contacts = lead.contact_names ?? [];
  const hasFunnelScores =
    lead.score_strategisch != null &&
    lead.score_politiek != null &&
    lead.score_positie != null;

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white rounded-xl border border-border p-3 hover:border-primary-200 hover:shadow-sm transition-all space-y-1.5"
    >
      <p className="text-sm font-medium text-text line-clamp-2">{lead.title}</p>

      {lead.organization && (
        <p className="text-xs text-text-secondary truncate">
          {lead.externe_organisatie?.naam ?? lead.organization}
        </p>
      )}

      {lead.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 overflow-hidden max-h-[3.25rem]">
          {lead.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="inline-block rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-text-secondary truncate max-w-full"
            >
              {tag}
            </span>
          ))}
          {lead.tags.length > 3 && (
            <span className="text-[10px] text-text-secondary shrink-0">+{lead.tags.length - 3}</span>
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
                <Users className="h-3 w-3" />
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
            <Calendar className="h-3 w-3" />
            {formatDateShort(lead.next_action_date)}
          </span>
        )}

        {lead.attachment_count > 0 && (
          <span className="inline-flex items-center gap-0.5 ml-auto">
            <Paperclip className="h-3 w-3" />
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
    </button>
  );
}
