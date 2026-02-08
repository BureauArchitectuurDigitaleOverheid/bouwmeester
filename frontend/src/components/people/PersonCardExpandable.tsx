import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { clsx } from 'clsx';
import { Mail, Briefcase, Shield, Pencil, CheckCircle2, Circle, FileText, Loader2, Bot, MessageSquare, Terminal } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { SendMessageModal } from '@/components/common/SendMessageModal';
import { usePersonSummary } from '@/hooks/usePeople';
import { ROL_LABELS, NODE_TYPE_COLORS, STAKEHOLDER_ROL_LABELS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
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
  /** Extra badge shown on the right side (e.g. stakeholder role) */
  extraBadge?: React.ReactNode;
}

export function PersonCardExpandable({ person, onEditPerson, onDragStartPerson, isManager, extraBadge }: PersonCardExpandableProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [messageOpen, setMessageOpen] = useState(false);
  const navigate = useNavigate();
  const { nodeLabel } = useVocabulary();
  const { data: summary, isLoading: summaryLoading } = usePersonSummary(expanded ? person.id : null);

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
            {isManager && (
              <Badge
                variant={person.rol === 'minister' || person.rol === 'staatssecretaris' ? 'purple' : 'blue'}
                className="text-[10px] px-1.5 py-0 shrink-0"
              >
                {person.rol === 'minister' || person.rol === 'staatssecretaris' ? 'Bewindspersoon' : 'Manager'}
              </Badge>
            )}
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
            {person.functie && (
              <span className="flex items-center gap-1">
                <Briefcase className="h-3 w-3" />
                {person.functie}
              </span>
            )}
            {person.rol && (
              <span className="flex items-center gap-1">
                <Shield className="h-3 w-3" />
                {ROL_LABELS[person.rol] || person.rol}
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
                      <div key={task.id} className="flex items-center gap-2 text-text">
                        <span className={clsx('h-1.5 w-1.5 rounded-full shrink-0', PRIORITY_DOT_COLORS[task.priority] || 'bg-gray-300')} />
                        <span className="truncate">{task.title}</span>
                        {task.due_date && (
                          <span className="text-text-secondary shrink-0 ml-auto">
                            {new Date(task.due_date).toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' })}
                          </span>
                        )}
                      </div>
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
                          navigate(`/nodes/${node.node_id}`);
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

              {/* No tasks and no nodes */}
              {summary.open_task_count === 0 && summary.done_task_count === 0 && summary.stakeholder_nodes.length === 0 && (
                <p className="text-text-secondary">Geen taken of dossiers.</p>
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
