import { useState, useCallback } from 'react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { PersonCardExpandable } from '@/components/people/PersonCardExpandable';
import { Icon } from '@/components/nldd/Icon';
import { useOrganisatieEenheid, useOrganisatiePersonenRecursive } from '@/hooks/useOrganisatie';
import { formatOrganisatieType, ORGANISATIE_TYPE_BADGE_COLORS, formatFunctie } from '@/types';
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
        'border rounded-lg p-2 sm:p-3 space-y-2 transition-all duration-150',
        orgTypeBg(group.eenheid.type),
        dragOver
          ? 'border-primary-400 ring-2 ring-primary-200'
          : 'border-border',
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Group header. A plain button rather than NlddButton: the label is a
          composite of an icon, a badge, a name and a count, none of which
          nldd-button's text/icon slots can carry together (its children only
          reach the `text` slot, not a default slot for arbitrary content). */}
      <button
        className="flex items-center gap-2 w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <Icon name={expanded ? 'ChevronDown' : 'ChevronRight'} size="sm" />
        <Badge variant={ORGANISATIE_TYPE_BADGE_COLORS[group.eenheid.type] || 'gray'}>
          {formatOrganisatieType(group.eenheid.type)}
        </Badge>
        <nldd-text size="sm" weight="medium" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {group.eenheid.naam}
        </nldd-text>
        <nldd-text size="xs" color="secondary">({totalCount})</nldd-text>
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
    return <EmptyState icon="apartment-building" title="Eenheid niet gevonden" />;
  }

  return (
    <nldd-container gap="24">
      {/* Header. The sm-and-up side-by-side vs. stacked-below-sm split has no
          nldd-container equivalent (layout is one fixed mode, not responsive),
          so the two top-level rows keep their plain flex wrapper; everything
          inside converts. */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <nldd-container gap="4">
          <Badge
            variant={ORGANISATIE_TYPE_BADGE_COLORS[eenheid.type] || 'gray'}
            dot
          >
            {formatOrganisatieType(eenheid.type)}
          </Badge>
          <nldd-title size={4}><h2>{eenheid.naam}</h2></nldd-title>
          {eenheid.manager && (
            <nldd-text size="sm" color="secondary">
              {eenheid.manager.naam}{eenheid.manager.functie ? ` — ${formatFunctie(eenheid.manager.functie)}` : ''}
            </nldd-text>
          )}
          {eenheid.beschrijving && (
            <RichTextDisplay content={eenheid.beschrijving} fallback="" />
          )}
          {/* Externe-data velden uit TOOI/Ministeries.csv/handmatig. A <dl> is
              the correct semantic element for this label/value list, and
              nldd-text doesn't replace dt/dd — only the grid/spacing utilities
              that arranged them convert, via inline style since nldd-container
              doesn't do a two-column label/value CSS grid. */}
          {(eenheid.afkorting ||
            eenheid.oin ||
            eenheid.fte_aantal ||
            eenheid.website ||
            eenheid.kvk_nummer ||
            eenheid.tooi_uri) && (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
              {eenheid.afkorting && (
                <>
                  <dt className="text-text-secondary">Afkorting</dt>
                  <dd>{eenheid.afkorting}</dd>
                </>
              )}
              {eenheid.oin && (
                <>
                  <dt className="text-text-secondary">OIN</dt>
                  <dd className="font-mono">{eenheid.oin}</dd>
                </>
              )}
              {eenheid.fte_aantal != null && (
                <>
                  <dt className="text-text-secondary">FTE</dt>
                  <dd>{eenheid.fte_aantal}</dd>
                </>
              )}
              {eenheid.website && (
                <>
                  <dt className="text-text-secondary">Website</dt>
                  <dd>
                    <nldd-link href={eenheid.website} target="_blank" text={eenheid.website} size="xs" style={{ maxWidth: '400px', display: 'block' }} />
                  </dd>
                </>
              )}
              {eenheid.kvk_nummer && (
                <>
                  <dt className="text-text-secondary">KvK</dt>
                  <dd className="font-mono">{eenheid.kvk_nummer}</dd>
                </>
              )}
              {eenheid.tooi_uri && (
                <>
                  <dt className="text-text-secondary">TOOI</dt>
                  <dd>
                    <nldd-link href={eenheid.tooi_uri} target="_blank" text={eenheid.tooi_uri} size="xs" className="font-mono" style={{ maxWidth: '400px', display: 'block' }} />
                  </dd>
                </>
              )}
            </dl>
          )}
        </nldd-container>
        <nldd-container layout="row" gap="8" width="fit-content">
          <Button variant="secondary" size="sm" icon="pencil" onClick={onEdit}>
            Bewerken
          </Button>
          <Button variant="danger" size="sm" icon="trash" onClick={onDelete}>
            Verwijderen
          </Button>
        </nldd-container>
      </div>

      {/* Action buttons */}
      <nldd-container layout="wrap" gap="8">
        <Button variant="secondary" size="sm" icon="plus" onClick={onAddChild}>
          Subeenheid toevoegen
        </Button>
        <Button variant="secondary" size="sm" icon="person" onClick={onAddPerson}>
          Persoon toevoegen
        </Button>
        <Button variant="secondary" size="sm" icon="sparkles" onClick={onAddAgent}>
          Agent toevoegen
        </Button>
      </nldd-container>

      {/* People — recursive grouped view */}
      <nldd-container gap="12">
        <nldd-container layout="row" gap="8" vertical-alignment="center">
          <Icon name="Users" size="sm" />
          <nldd-title size={6}>
            <h3>Personen ({personenCount}){agentCount > 0 && ` · Agents (${agentCount})`}</h3>
          </nldd-title>
        </nldd-container>

        {!personenGroup || totalCount === 0 ? (
          <nldd-text size="sm" color="secondary">
            Geen personen of agents gekoppeld aan deze eenheid.
          </nldd-text>
        ) : (
          <PersonGroupSection
            group={personenGroup}
            isRoot={true}
            onEditPerson={onEditPerson}
            onDragStartPerson={onDragStartPerson}
            onDropPerson={onDropPerson}
          />
        )}
      </nldd-container>
    </nldd-container>
  );
}
