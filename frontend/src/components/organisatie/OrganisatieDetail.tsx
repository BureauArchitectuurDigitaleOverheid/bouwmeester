import { Pencil, Trash2, Plus, Users, Building2, User, Mail, Briefcase, Shield, ChevronDown, ChevronRight, Copy, Check, CheckCircle2, Circle, FileText, Loader2 } from 'lucide-react';
import { useState, useCallback } from 'react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useOrganisatieEenheid, useOrganisatiePersonenRecursive } from '@/hooks/useOrganisatie';
import { usePersonSummary } from '@/hooks/usePeople';
import { ORGANISATIE_TYPE_LABELS, ROL_LABELS, TASK_PRIORITY_COLORS, NODE_TYPE_LABELS, NODE_TYPE_COLORS, STAKEHOLDER_ROL_LABELS } from '@/types';
import type { Person, OrganisatieEenheidPersonenGroup } from '@/types';

const TYPE_BADGE_COLORS: Record<string, 'blue' | 'purple' | 'amber' | 'cyan' | 'green' | 'gray'> = {
  ministerie: 'blue',
  directoraat_generaal: 'purple',
  directie: 'amber',
  afdeling: 'cyan',
  team: 'green',
};

const TYPE_BG_COLORS: Record<string, string> = {
  ministerie: 'bg-blue-50/40',
  directoraat_generaal: 'bg-purple-50/40',
  directie: 'bg-amber-50/40',
  afdeling: 'bg-cyan-50/40',
  team: 'bg-emerald-50/40',
};

function countAllPersonen(group: OrganisatieEenheidPersonenGroup): number {
  return group.personen.length + group.children.reduce((sum, child) => sum + countAllPersonen(child), 0);
}

function hasAnyPersonen(group: OrganisatieEenheidPersonenGroup): boolean {
  return group.personen.length > 0 || group.children.some(hasAnyPersonen);
}

interface PersonCardProps {
  person: Person;
  onEditPerson: (person: Person) => void;
  onDragStartPerson?: (e: React.DragEvent, person: Person) => void;
  isManager?: boolean;
}

const PRIORITY_DOT_COLORS: Record<string, string> = {
  kritiek: 'bg-red-500',
  hoog: 'bg-orange-400',
  normaal: 'bg-blue-400',
  laag: 'bg-gray-300',
};

function PersonCardInner({ person, onEditPerson, onDragStartPerson, isManager }: PersonCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
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
      draggable
      onDragStart={onDragStartPerson ? (e: React.DragEvent) => onDragStartPerson(e, person) : undefined}
    >
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center h-9 w-9 rounded-full bg-primary-100 text-primary-700 text-sm font-medium shrink-0">
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-text truncate">
              {person.naam}
            </p>
            {isManager && (
              <Badge variant="blue" className="text-[10px] px-1.5 py-0 shrink-0">
                Manager
              </Badge>
            )}
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
                      <div key={node.node_id} className="flex items-center gap-2 text-text">
                        <FileText className="h-3 w-3 text-text-secondary shrink-0" />
                        <span className="truncate">{node.node_title}</span>
                        <Badge
                          variant={(NODE_TYPE_COLORS[node.node_type as keyof typeof NODE_TYPE_COLORS] || 'gray') as 'blue' | 'green' | 'purple' | 'amber' | 'cyan' | 'rose' | 'slate' | 'gray'}
                          className="text-[10px] px-1.5 py-0 shrink-0"
                        >
                          {NODE_TYPE_LABELS[node.node_type as keyof typeof NODE_TYPE_LABELS] || node.node_type}
                        </Badge>
                        <span className="text-text-secondary shrink-0 ml-auto">
                          {STAKEHOLDER_ROL_LABELS[node.stakeholder_rol] || node.stakeholder_rol}
                        </span>
                      </div>
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
        </div>
      )}
    </Card>
  );
}

interface PersonGroupSectionProps {
  group: OrganisatieEenheidPersonenGroup;
  isRoot: boolean;
  onEditPerson: (person: Person) => void;
  onDragStartPerson?: (e: React.DragEvent, person: Person) => void;
  onDropPerson?: (personId: string, targetNodeId: string) => void;
}

function PersonGroupSection({ group, isRoot, onEditPerson, onDragStartPerson, onDropPerson }: PersonGroupSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const [dragOver, setDragOver] = useState(false);
  const totalCount = countAllPersonen(group);
  const managerId = group.eenheid.manager?.id;

  // Split people into manager (shown first with distinct style) and others
  const managerPerson = managerId ? group.personen.find((p) => p.id === managerId) : null;
  const otherPersonen = managerId ? group.personen.filter((p) => p.id !== managerId) : group.personen;

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (!onDropPerson) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(true);
  }, [onDropPerson]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    // Only clear if we're actually leaving this element (not entering a child)
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (!onDropPerson) return;
    const personId = e.dataTransfer.getData('application/person-id');
    if (personId) {
      onDropPerson(personId, group.eenheid.id);
    }
  }, [onDropPerson, group.eenheid.id]);

  // Hide groups with no people in entire subtree
  if (!hasAnyPersonen(group)) return null;

  if (isRoot) {
    return (
      <div
        className="space-y-2"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Manager at root level (shown first, distinct style) */}
        {managerPerson && (
          <PersonCardInner
            person={managerPerson}
            onEditPerson={onEditPerson}
            onDragStartPerson={onDragStartPerson}
            isManager
          />
        )}

        {/* Direct people at root level */}
        {otherPersonen.map((person) => (
          <PersonCardInner
            key={person.id}
            person={person}
            onEditPerson={onEditPerson}
            onDragStartPerson={onDragStartPerson}
          />
        ))}

        {/* Child groups */}
        {group.children.map((child) => (
          <PersonGroupSection
            key={child.eenheid.id}
            group={child}
            isRoot={false}
            onEditPerson={onEditPerson}
            onDragStartPerson={onDragStartPerson}
            onDropPerson={onDropPerson}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className={clsx(
        'border rounded-lg p-3 space-y-2 transition-all duration-150',
        TYPE_BG_COLORS[group.eenheid.type] || '',
        dragOver
          ? 'border-primary-400 ring-2 ring-primary-200'
          : 'border-border',
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Group header */}
      <button
        className="flex items-center gap-2 w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-text-secondary shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-text-secondary shrink-0" />
        )}
        <Badge
          variant={TYPE_BADGE_COLORS[group.eenheid.type] || 'gray'}
          className="text-[10px] px-1.5 py-0"
        >
          {ORGANISATIE_TYPE_LABELS[group.eenheid.type] || group.eenheid.type}
        </Badge>
        <span className="text-sm font-medium text-text truncate">{group.eenheid.naam}</span>
        <span className="text-xs text-text-secondary">({totalCount})</span>
      </button>

      {expanded && (
        <div className="space-y-2 ml-1">
          {/* Manager at top of group */}
          {managerPerson && (
            <PersonCardInner
              person={managerPerson}
              onEditPerson={onEditPerson}
              onDragStartPerson={onDragStartPerson}
              isManager
            />
          )}

          {/* Direct people */}
          {otherPersonen.map((person) => (
            <PersonCardInner
              key={person.id}
              person={person}
              onEditPerson={onEditPerson}
              onDragStartPerson={onDragStartPerson}
            />
          ))}

          {/* Nested child groups */}
          {group.children.map((child) => (
            <PersonGroupSection
              key={child.eenheid.id}
              group={child}
              isRoot={false}
              onEditPerson={onEditPerson}
              onDragStartPerson={onDragStartPerson}
              onDropPerson={onDropPerson}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface OrganisatieDetailProps {
  selectedId: string;
  onEdit: () => void;
  onDelete: () => void;
  onAddChild: () => void;
  onAddPerson: () => void;
  onEditPerson: (person: Person) => void;
  onDragStartPerson?: (e: React.DragEvent, person: Person) => void;
  onDropPerson?: (personId: string, targetNodeId: string) => void;
}

export function OrganisatieDetail({
  selectedId,
  onEdit,
  onDelete,
  onAddChild,
  onAddPerson,
  onEditPerson,
  onDragStartPerson,
  onDropPerson,
}: OrganisatieDetailProps) {
  const { data: eenheid, isLoading } = useOrganisatieEenheid(selectedId);
  const { data: personenGroup } = useOrganisatiePersonenRecursive(selectedId);

  const totalCount = personenGroup ? countAllPersonen(personenGroup) : 0;

  if (isLoading) {
    return <LoadingSpinner className="py-12" />;
  }

  if (!eenheid) {
    return (
      <div className="text-center py-12 text-text-secondary">
        <Building2 className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">Eenheid niet gevonden.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Badge
              variant={TYPE_BADGE_COLORS[eenheid.type] || 'gray'}
              dot
            >
              {ORGANISATIE_TYPE_LABELS[eenheid.type] || eenheid.type}
            </Badge>
          </div>
          <h2 className="text-xl font-semibold text-text">{eenheid.naam}</h2>
          {eenheid.manager && (
            <p className="text-sm text-text-secondary mt-0.5">
              {eenheid.manager.naam}{eenheid.manager.functie ? ` — ${eenheid.manager.functie}` : ''}
            </p>
          )}
          {eenheid.beschrijving && (
            <p className="text-sm text-text-secondary mt-1">{eenheid.beschrijving}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={<Pencil className="h-3.5 w-3.5" />}
            onClick={onEdit}
          >
            Bewerken
          </Button>
          <Button
            variant="danger"
            size="sm"
            icon={<Trash2 className="h-3.5 w-3.5" />}
            onClick={onDelete}
          >
            Verwijderen
          </Button>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus className="h-3.5 w-3.5" />}
          onClick={onAddChild}
        >
          Subeenheid toevoegen
        </Button>
        <Button
          variant="secondary"
          size="sm"
          icon={<User className="h-3.5 w-3.5" />}
          onClick={onAddPerson}
        >
          Persoon toevoegen
        </Button>
      </div>

      {/* People — recursive grouped view */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Users className="h-4 w-4 text-text-secondary" />
          <h3 className="text-sm font-semibold text-text">
            Personen ({totalCount})
          </h3>
        </div>

        {!personenGroup || totalCount === 0 ? (
          <p className="text-sm text-text-secondary">
            Geen personen gekoppeld aan deze eenheid.
          </p>
        ) : (
          <PersonGroupSection
            group={personenGroup}
            isRoot={true}
            onEditPerson={onEditPerson}
            onDragStartPerson={onDragStartPerson}
            onDropPerson={onDropPerson}
          />
        )}
      </div>
    </div>
  );
}
