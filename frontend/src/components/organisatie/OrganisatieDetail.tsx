import { Pencil, Trash2, Plus, Users, Building2, User, Bot, ChevronDown, ChevronRight } from 'lucide-react';
import { useState, useCallback } from 'react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { PersonCardExpandable } from '@/components/people/PersonCardExpandable';
import { useOrganisatieEenheid, useOrganisatiePersonenRecursive } from '@/hooks/useOrganisatie';
import { ORGANISATIE_TYPE_LABELS, ORGANISATIE_TYPE_BADGE_COLORS, formatFunctie } from '@/types';
import type { Person, OrganisatieEenheidPersonenGroup } from '@/types';

/** Org types where the manager role is labeled "Coördinator" instead of "Manager". */
const COORDINATOR_TYPES = new Set(['cluster', 'team']);
const BEWINDSPERSOON_FUNCTIES = new Set(['minister', 'staatssecretaris']);

function managerLabelForType(orgType: string, functie?: string | null): string {
  if (functie && BEWINDSPERSOON_FUNCTIES.has(functie)) return 'Bewindspersoon';
  return COORDINATOR_TYPES.has(orgType) ? 'Coördinator' : 'Manager';
}

// Tailwind bg classes for each badge color (green uses emerald in our design system)
const BADGE_BG_CLASS: Record<string, string> = {
  blue: 'bg-blue-50/40', purple: 'bg-purple-50/40', amber: 'bg-amber-50/40',
  cyan: 'bg-cyan-50/40', green: 'bg-emerald-50/40', gray: 'bg-gray-50/40',
};
function orgTypeBg(type: string): string {
  return BADGE_BG_CLASS[ORGANISATIE_TYPE_BADGE_COLORS[type] ?? 'gray'] ?? '';
}

function countAllPersonen(group: OrganisatieEenheidPersonenGroup): number {
  return group.personen.length + group.children.reduce((sum, child) => sum + countAllPersonen(child), 0);
}

function countAgents(group: OrganisatieEenheidPersonenGroup): number {
  return group.personen.filter((p) => p.is_agent).length + group.children.reduce((sum, child) => sum + countAgents(child), 0);
}

function hasAnyPersonen(group: OrganisatieEenheidPersonenGroup): boolean {
  return group.personen.length > 0 || group.children.some(hasAnyPersonen);
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
  const otherPersonen = (managerId ? group.personen.filter((p) => p.id !== managerId) : group.personen)
    .slice()
    .sort((a, b) => {
      if (a.is_agent === b.is_agent) return 0;
      return a.is_agent ? 1 : -1;
    });

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
          <PersonCardExpandable
            person={managerPerson}
            onEditPerson={onEditPerson}
            onDragStartPerson={onDragStartPerson}
            isManager
            managerLabel={managerLabelForType(group.eenheid.type, managerPerson.functie)}
            showPlacementActions
          />
        )}

        {/* Direct people at root level */}
        {otherPersonen.map((person) => (
          <PersonCardExpandable
            key={person.id}
            person={person}
            onEditPerson={onEditPerson}
            onDragStartPerson={onDragStartPerson}
            showPlacementActions
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
        orgTypeBg(group.eenheid.type),
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
          variant={ORGANISATIE_TYPE_BADGE_COLORS[group.eenheid.type] || 'gray'}
          className="text-xs px-2 py-0.5"
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
            <PersonCardExpandable
              person={managerPerson}
              onEditPerson={onEditPerson}
              onDragStartPerson={onDragStartPerson}
              isManager
              managerLabel={managerLabelForType(group.eenheid.type, managerPerson.functie)}
              showPlacementActions
            />
          )}

          {/* Direct people */}
          {otherPersonen.map((person) => (
            <PersonCardExpandable
              key={person.id}
              person={person}
              onEditPerson={onEditPerson}
              onDragStartPerson={onDragStartPerson}
              showPlacementActions
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
  onAddAgent: () => void;
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
  onAddAgent,
  onEditPerson,
  onDragStartPerson,
  onDropPerson,
}: OrganisatieDetailProps) {
  const { data: eenheid, isLoading } = useOrganisatieEenheid(selectedId);
  const { data: personenGroup } = useOrganisatiePersonenRecursive(selectedId);

  const totalCount = personenGroup ? countAllPersonen(personenGroup) : 0;
  const agentCount = personenGroup ? countAgents(personenGroup) : 0;
  const personenCount = totalCount - agentCount;

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
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Badge
              variant={ORGANISATIE_TYPE_BADGE_COLORS[eenheid.type] || 'gray'}
              dot
            >
              {ORGANISATIE_TYPE_LABELS[eenheid.type] || eenheid.type}
            </Badge>
          </div>
          <h2 className="text-xl font-semibold text-text">{eenheid.naam}</h2>
          {eenheid.manager && (
            <p className="text-sm text-text-secondary mt-0.5">
              {eenheid.manager.naam}{eenheid.manager.functie ? ` — ${formatFunctie(eenheid.manager.functie)}` : ''}
            </p>
          )}
          {eenheid.beschrijving && (() => {
            // Extract plain text from TipTap JSON, or show as-is for plain text
            let displayText = eenheid.beschrijving;
            try {
              const parsed = JSON.parse(eenheid.beschrijving);
              if (parsed?.type === 'doc' && Array.isArray(parsed.content)) {
                displayText = parsed.content
                  .map((block: { content?: { text?: string }[] }) =>
                    block.content?.map((c) => c.text ?? '').join('') ?? ''
                  )
                  .filter(Boolean)
                  .join('\n');
              }
            } catch {
              // plain text — use as-is
            }
            return displayText ? (
              <p className="text-sm text-text-secondary mt-1">{displayText}</p>
            ) : null;
          })()}
        </div>
        <div className="flex items-center gap-2 shrink-0">
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
      <div className="flex items-center gap-2 flex-wrap">
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
        <Button
          variant="secondary"
          size="sm"
          icon={<Bot className="h-3.5 w-3.5" />}
          onClick={onAddAgent}
        >
          Agent toevoegen
        </Button>
      </div>

      {/* People — recursive grouped view */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Users className="h-4 w-4 text-text-secondary" />
          <h3 className="text-sm font-semibold text-text">
            Personen ({personenCount}){agentCount > 0 && ` · Agents (${agentCount})`}
          </h3>
        </div>

        {!personenGroup || totalCount === 0 ? (
          <p className="text-sm text-text-secondary">
            Geen personen of agents gekoppeld aan deze eenheid.
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
