import { useState, useCallback } from 'react';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { PersonCardExpandable } from '@/components/people/PersonCardExpandable';
import { Icon } from '@/components/nldd/Icon';
import { useOrganisatieEenheid, useOrganisatiePersonenRecursive } from '@/hooks/useOrganisatie';
import { usePermissions } from '@/hooks/usePermissions';
import { formatOrganisatieType, ORGANISATIE_TYPE_BADGE_COLORS, formatFunctie } from '@/types';
import type { Person, OrganisatieEenheidPersonenGroup } from '@/types';

/** Org types where the manager role is labeled "Coördinator" instead of "Manager". */
const COORDINATOR_TYPES = new Set(['cluster', 'team']);
const BEWINDSPERSOON_FUNCTIES = new Set(['minister', 'staatssecretaris']);

function managerLabelForType(orgType: string, functie?: string | null): string {
  if (functie && BEWINDSPERSOON_FUNCTIES.has(functie)) return 'Bewindspersoon';
  return COORDINATOR_TYPES.has(orgType) ? 'Coördinator' : 'Manager';
}

// Rijkshuisstijl primitive per badge color, at 40% opacity against the page
// background, mirroring Badge's own color families (see ORGANISATIE_TYPE_BADGE_COLORS).
const BADGE_TINT_PRIMITIVE: Record<string, string> = {
  blue: 'hemelblauw', purple: 'paars', amber: 'oranje',
  cyan: 'lichtblauw', green: 'mintgroen', gray: 'coolgray',
};
function orgTypeBg(type: string): string {
  const primitive = BADGE_TINT_PRIMITIVE[ORGANISATIE_TYPE_BADGE_COLORS[type] ?? 'gray'] ?? 'coolgray';
  return `color-mix(in oklch, var(--primitives-color-${primitive}-50) 40%, transparent)`;
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
      <nldd-container
        gap="8"
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
      </nldd-container>
    );
  }

  return (
    // A plain div, not nldd-box: the drag-over ring highlight and the
    // per-org-type tint (orgTypeBg) are dynamic border/ring colors with no
    // nldd-box equivalent (only background="tinted"/"base"/"critical").
    // The sm-and-up padding bump has no nldd-container equivalent for a plain
    // div, so it stays a small responsive utility class; everything else is
    // inline since it depends on drag state.
    <div
      className="org-group-padding"
      style={{
        borderRadius: '8px',
        transition: 'all 150ms',
        backgroundColor: orgTypeBg(group.eenheid.type),
        border: dragOver
          ? '1px solid var(--primitives-color-accent-400)'
          : '1px solid var(--primitives-color-neutral-50)',
        boxShadow: dragOver ? '0 0 0 2px var(--primitives-color-accent-200)' : undefined,
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <nldd-container gap="8">
        {/* Group header. A plain button rather than NlddButton: the label is a
            composite of an icon, a badge, a name and a count, none of which
            nldd-button's text/icon slots can carry together (its children only
            reach the `text` slot, not a default slot for arbitrary content).
            `plain-button` strips the user-agent chrome that would otherwise
            box in the whole header, keeping the tab stop and focus ring.
            width: 100% stays inline: nldd-container's width="full" fills the
            parent, not the host button's own box. */}
        <button
          className="plain-button"
          aria-expanded={expanded}
          style={{ width: '100%', textAlign: 'left' }}
          onClick={() => setExpanded(!expanded)}
        >
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            <Icon name={expanded ? 'ChevronDown' : 'ChevronRight'} size="sm" />
            <Badge variant={ORGANISATIE_TYPE_BADGE_COLORS[group.eenheid.type] || 'gray'}>
              {formatOrganisatieType(group.eenheid.type)}
            </Badge>
            <nldd-text size="sm" weight="medium" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {group.eenheid.naam}
            </nldd-text>
            <nldd-text size="xs" color="secondary">({totalCount})</nldd-text>
          </nldd-container>
        </button>

        {expanded && (
          // 4px left margin stays inline: no nldd-container margin equivalent,
          // and padding-left here would also inset the nested group's own
          // border/background rather than just this list.
          <div style={{ marginLeft: '4px' }}>
            <nldd-container gap="8">
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
            </nldd-container>
          </div>
        )}
      </nldd-container>
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
  const { isSuperAdmin } = usePermissions();
  const { data: personenGroup } = useOrganisatiePersonenRecursive(selectedId);

  const totalCount = personenGroup ? countAllPersonen(personenGroup) : 0;
  const agentCount = personenGroup ? countAgents(personenGroup) : 0;
  const personenCount = totalCount - agentCount;

  if (isLoading) {
    return <LoadingSpinner padding="48" />;
  }

  if (!eenheid) {
    return <EmptyState icon="apartment-building" title="Eenheid niet gevonden" />;
  }

  return (
    <nldd-container gap="24">
      {/* Header. The sm-and-up side-by-side vs. stacked-below-sm split has no
          nldd-container equivalent (layout is one fixed mode, not responsive),
          so the two top-level rows keep a plain flex wrapper and everything
          inside it is nldd. sm-row-header (utilities.css) carries the `sm`-and-up
          half of the breakpoint switch. */}
      <div className="sm-row-header" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
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
              nldd-text doesn't replace dt/dd. The grid is an inline style
              because nldd-container doesn't do a two-column label/value CSS
              grid. */}
          {(eenheid.afkorting ||
            eenheid.oin ||
            eenheid.fte_aantal ||
            eenheid.website ||
            eenheid.kvk_nummer ||
            eenheid.tooi_uri) && (
            <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', columnGap: '16px', rowGap: '4px', fontSize: '12px' }}>
              {eenheid.afkorting && (
                <>
                  <dt style={{ color: 'var(--primitives-color-neutral-700)' }}>Afkorting</dt>
                  <dd>{eenheid.afkorting}</dd>
                </>
              )}
              {eenheid.oin && (
                <>
                  <dt style={{ color: 'var(--primitives-color-neutral-700)' }}>OIN</dt>
                  <dd className="font-mono">{eenheid.oin}</dd>
                </>
              )}
              {eenheid.fte_aantal != null && (
                <>
                  <dt style={{ color: 'var(--primitives-color-neutral-700)' }}>FTE</dt>
                  <dd>{eenheid.fte_aantal}</dd>
                </>
              )}
              {eenheid.website && (
                <>
                  <dt style={{ color: 'var(--primitives-color-neutral-700)' }}>Website</dt>
                  <dd>
                    <nldd-link href={eenheid.website} target="_blank" text={eenheid.website} size="xs" style={{ maxWidth: '400px', display: 'block' }} />
                  </dd>
                </>
              )}
              {eenheid.kvk_nummer && (
                <>
                  <dt style={{ color: 'var(--primitives-color-neutral-700)' }}>KvK</dt>
                  <dd className="font-mono">{eenheid.kvk_nummer}</dd>
                </>
              )}
              {eenheid.tooi_uri && (
                <>
                  <dt style={{ color: 'var(--primitives-color-neutral-700)' }}>TOOI</dt>
                  <dd>
                    <nldd-link href={eenheid.tooi_uri} target="_blank" text={eenheid.tooi_uri} size="xs" className="font-mono" style={{ maxWidth: '400px', display: 'block' }} />
                  </dd>
                </>
              )}
            </dl>
          )}
        </nldd-container>
        <nldd-container layout="row" gap="8">
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
        {isSuperAdmin && (
          <Button variant="secondary" size="sm" icon="sparkles" onClick={onAddAgent}>
            Agent toevoegen
          </Button>
        )}
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
