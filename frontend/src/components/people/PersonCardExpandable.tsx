import { useState, useCallback } from 'react';
import { clsx } from 'clsx';
import { Mail, Briefcase, Pencil, CheckCircle2, Circle, FileText, Loader2, Bot, MessageSquare, Terminal, Building2, X } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { SendMessageModal } from '@/components/common/SendMessageModal';
import { usePersonSummary, usePersonOrganisaties, useUpdatePersonOrganisatie, useRemovePersonOrganisatie } from '@/hooks/usePeople';
import { FUNCTIE_LABELS, NODE_TYPE_COLORS, STAKEHOLDER_ROL_LABELS, DIENSTVERBAND_LABELS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { formatDateShort, todayISO } from '@/utils/dates';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import type { Person } from '@/types';

const PRIORITY_DOT_COLORS: Record<string, string> = {
  kritiek: 'bg-red-500',
  hoog: 'bg-orange-400',
  normaal: 'bg-blue-400',
  laag: 'bg-gray-300',
};

interface PersonCardExpandableProps {
  person: Person;
  onEditPerson?: (person: Person) => void;
  onDragStartPerson?: (e: React.DragEvent, person: Person) => void;
  isManager?: boolean;
  /** Override the manager badge label (e.g. "Coördinator" for teams) */
  managerLabel?: string;
  /** Extra badge shown on the right side (e.g. stakeholder role) */
  extraBadge?: React.ReactNode;
}

export function PersonCardExpandable({ person, onEditPerson, onDragStartPerson, isManager, managerLabel, extraBadge }: PersonCardExpandableProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [messageOpen, setMessageOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const { nodeLabel } = useVocabulary();
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();
  const { data: summary, isLoading: summaryLoading } = usePersonSummary(expanded ? person.id : null);
  const { data: placements } = usePersonOrganisaties(expanded ? person.id : null);
  const endPlacement = useUpdatePersonOrganisatie();
  const removePlacement = useRemovePersonOrganisatie();

  const handleCopyEmail = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (person.email) {
      navigator.clipboard.writeText(person.email);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }, [person.email]);

  const initials = person.naam
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <Card
      hoverable
      onClick={() => setExpanded(!expanded)}
      draggable={!!onDragStartPerson}
      onDragStart={onDragStartPerson ? (e: React.DragEvent) => onDragStartPerson(e, person) : undefined}
    >
      <div className="flex items-center gap-3">
        {person.is_agent ? (
          <div className="relative flex items-center justify-center h-9 w-9 rounded-full bg-violet-100 text-violet-700 shrink-0">
            <Bot className="h-4.5 w-4.5" />
          </div>
        ) : (
          <div className="flex items-center justify-center h-9 w-9 rounded-full bg-primary-100 text-primary-700 text-sm font-medium shrink-0">
            {initials}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-text truncate">
              {person.naam}
            </p>
            {person.is_agent && (
              <Badge variant="purple" className="text-[10px] px-1.5 py-0 shrink-0">
                Agent
              </Badge>
            )}
            {isManager && (() => {
              const isBewindspersoon = person.functie === 'minister' || person.functie === 'staatssecretaris';
              const label = isBewindspersoon ? 'Bewindspersoon' : (managerLabel ?? 'Manager');
              return (
                <Badge
                  variant={isBewindspersoon ? 'purple' : 'blue'}
                  className="text-[10px] px-1.5 py-0 shrink-0"
                >
                  {label}
                </Badge>
              );
            })()}
            {extraBadge && <div className="shrink-0 ml-auto">{extraBadge}</div>}
          </div>
          <div className="flex items-center gap-3 text-xs text-text-secondary mt-0.5">
            {person.email && (
              <button
                className="flex items-center gap-1 hover:text-primary-600 transition-colors"
                onClick={handleCopyEmail}
                title="Klik om e-mail te kopiëren"
              >
                <Mail className="h-3 w-3" />
                {copied ? 'Gekopieerd!' : person.email}
              </button>
            )}
            {person.functie && !person.is_agent && (
              <span className="flex items-center gap-1">
                <Briefcase className="h-3 w-3" />
                {FUNCTIE_LABELS[person.functie] || person.functie.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </span>
            )}
            {person.description && person.is_agent && (
              <span className="flex items-center gap-1 truncate">
                <Briefcase className="h-3 w-3" />
                {person.description}
              </span>
            )}
          </div>
        </div>
        {/* Prominent message/prompt button — always visible */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            setMessageOpen(true);
          }}
          className={clsx(
            'shrink-0 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            person.is_agent
              ? 'bg-violet-100 text-violet-700 hover:bg-violet-200'
              : 'bg-primary-100 text-primary-700 hover:bg-primary-200',
          )}
          title={person.is_agent ? 'Prompt sturen' : 'Bericht sturen'}
        >
          {person.is_agent ? <Terminal className="h-3.5 w-3.5" /> : <MessageSquare className="h-3.5 w-3.5" />}
          {person.is_agent ? 'Prompt' : 'Bericht'}
        </button>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-border text-xs">
          {summaryLoading ? (
            <div className="flex items-center gap-2 text-text-secondary py-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>Laden...</span>
            </div>
          ) : summary ? (
            <div className="space-y-3">
              {/* Tasks section */}
              <div>
                <div className="flex items-center gap-3 text-text-secondary">
                  <span className="flex items-center gap-1">
                    <Circle className="h-3 w-3" />
                    {summary.open_task_count} open
                  </span>
                  <span className="flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3" />
                    {summary.done_task_count} afgerond
                  </span>
                </div>
                {summary.open_tasks.length > 0 && (
                  <div className="mt-1.5 space-y-1">
                    {summary.open_tasks.map((task) => (
                      <button
                        key={task.id}
                        className="flex items-center gap-2 text-text w-full text-left hover:text-primary-600 transition-colors rounded px-1 -mx-1 py-0.5 hover:bg-primary-50/50"
                        onClick={(e) => {
                          e.stopPropagation();
                          openTaskDetail(task.id);
                        }}
                      >
                        <span className={clsx('h-1.5 w-1.5 rounded-full shrink-0', PRIORITY_DOT_COLORS[task.priority] || 'bg-gray-300')} />
                        <span className="truncate">{task.title}</span>
                        {task.due_date && (
                          <span className="text-text-secondary shrink-0 ml-auto">
                            {formatDateShort(task.due_date)}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Stakeholder nodes section */}
              {summary.stakeholder_nodes.length > 0 && (
                <div>
                  <div className="space-y-1">
                    {summary.stakeholder_nodes.map((node) => (
                      <button
                        key={node.node_id}
                        className="flex items-center gap-2 text-text w-full text-left hover:text-primary-600 transition-colors rounded px-1 -mx-1 py-0.5 hover:bg-primary-50/50"
                        onClick={(e) => {
                          e.stopPropagation();
                          openNodeDetail(node.node_id);
                        }}
                      >
                        <FileText className="h-3 w-3 text-text-secondary shrink-0" />
                        <span className="truncate">{node.node_title}</span>
                        <Badge
                          variant={(NODE_TYPE_COLORS[node.node_type as keyof typeof NODE_TYPE_COLORS] || 'gray') as 'blue' | 'green' | 'purple' | 'amber' | 'cyan' | 'rose' | 'slate' | 'gray'}
                          className="text-[10px] px-1.5 py-0 shrink-0"
                        >
                          {nodeLabel(node.node_type)}
                        </Badge>
                        <span className="text-text-secondary shrink-0 ml-auto">
                          {STAKEHOLDER_ROL_LABELS[node.stakeholder_rol] || node.stakeholder_rol}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Org placements section */}
              {placements && placements.length > 0 && (
                <div>
                  <p className="text-text-secondary font-medium mb-1 flex items-center gap-1">
                    <Building2 className="h-3 w-3" />
                    Plaatsingen
                  </p>
                  <div className="space-y-1">
                    {placements.map((p) => (
                      <div key={p.id} className="flex items-center gap-2 text-text">
                        <span className="truncate">{p.organisatie_eenheid_naam}</span>
                        <Badge variant="gray" className="text-[10px] px-1.5 py-0 shrink-0">
                          {DIENSTVERBAND_LABELS[p.dienstverband] || p.dienstverband}
                        </Badge>
                        <div className="flex items-center gap-1 shrink-0 ml-auto">
                          {!p.eind_datum && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                endPlacement.mutate(
                                  {
                                    personId: person.id,
                                    placementId: p.id,
                                    data: { eind_datum: todayISO() },
                                  },
                                  { onError: () => alert('Plaatsing beëindigen mislukt.') },
                                );
                              }}
                              className="text-text-secondary hover:text-amber-600 transition-colors"
                              title="Plaatsing beëindigen"
                            >
                              <CheckCircle2 className="h-3 w-3" />
                            </button>
                          )}
                          {confirmDeleteId === p.id ? (
                            <span className="flex items-center gap-1 text-red-600">
                              <span>Zeker?</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  removePlacement.mutate(
                                    { personId: person.id, placementId: p.id },
                                    {
                                      onSettled: () => setConfirmDeleteId(null),
                                      onError: () => alert('Verwijderen mislukt.'),
                                    },
                                  );
                                }}
                                className="font-medium hover:underline"
                              >
                                Ja
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteId(null);
                                }}
                                className="text-text-secondary hover:text-text"
                              >
                                Nee
                              </button>
                            </span>
                          ) : (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setConfirmDeleteId(p.id);
                              }}
                              className="text-text-secondary hover:text-red-600 transition-colors"
                              title="Plaatsing verwijderen"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* No tasks and no nodes */}
              {summary.open_task_count === 0 && summary.done_task_count === 0 && summary.stakeholder_nodes.length === 0 && (!placements || placements.length === 0) && (
                <p className="text-text-secondary">Geen taken, dossiers of plaatsingen.</p>
              )}
            </div>
          ) : null}

          {/* Edit button */}
          {onEditPerson && (
            <div className="flex justify-end mt-2 pt-2 border-t border-border">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onEditPerson(person);
                }}
                className="flex items-center gap-1 text-text-secondary hover:text-text transition-colors"
                title="Bewerken"
              >
                <Pencil className="h-3 w-3" />
                <span>Bewerken</span>
              </button>
            </div>
          )}
        </div>
      )}

      <SendMessageModal
        open={messageOpen}
        onClose={() => setMessageOpen(false)}
        recipient={person}
      />
    </Card>
  );
}
