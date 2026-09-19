import { useEffect, useRef, useState } from 'react';
import { Badge } from '@/components/common/Badge';
import { Icon } from '@/components/nldd/Icon';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import type { OrganisatieEenheidTreeNode } from '@/types';
import { formatOrganisatieType, ORGANISATIE_TYPE_BADGE_COLORS } from '@/types';

function getTotalPersonenCount(node: OrganisatieEenheidTreeNode): number {
  return node.personen_count + node.children.reduce((sum, child) => sum + getTotalPersonenCount(child), 0);
}

interface TreeNodeProps {
  node: OrganisatieEenheidTreeNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAdd: (parentId: string) => void;
  onDropPerson?: (personId: string, targetNodeId: string) => void;
  depth?: number;
  searchTerm?: string;
  expandedByDefaultIds?: Set<string>;
}

function TreeNode({ node, selectedId, onSelect, onAdd, onDropPerson, depth = 0, searchTerm = '', expandedByDefaultIds }: TreeNodeProps) {
  // Default: alles dicht. Met 1437 TOOI-rijen + 470 organogram-scrapes wordt
  // de boom anders onleesbaar. Uitzondering: nodes op het pad naar de eigen
  // organisatie van de gebruiker staan wel open — dat is je entrypoint.
  // Bij een actieve zoekterm forceren we alles open zodat treffers zichtbaar zijn.
  const isHistorisch = !!node.geldig_tot;
  const defaultExpanded = expandedByDefaultIds?.has(node.id) ?? false;
  const isSearching = searchTerm.trim().length > 0;
  const [expanded, setExpanded] = useState(defaultExpanded);
  // expandedByDefaultIds wordt asynchroon berekend (auth + tree moeten beide
  // binnen zijn). Bij elke wijziging van de set updaten we de lokale state,
  // anders blijft de boom dicht omdat useState alleen de eerste init gebruikt.
  useEffect(() => {
    if (defaultExpanded) setExpanded(true);
  }, [defaultExpanded]);
  // Bij actieve zoekterm forceren we alles open zodat treffers zichtbaar zijn
  const effectiveExpanded = isSearching ? true : expanded;
  const [dragOver, setDragOver] = useState(false);
  const hasChildren = node.children.length > 0;
  const isSelected = selectedId === node.id;

  const handleDragOver = (e: React.DragEvent) => {
    if (!onDropPerson) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (!onDropPerson) return;
    const personId = e.dataTransfer.getData('application/person-id');
    if (personId) {
      onDropPerson(personId, node.id);
    }
  };

  const toggleRef = useRef<HTMLElement>(null);
  const selectRef = useRef<HTMLElement>(null);
  const addRef = useRef<HTMLElement>(null);
  useNlddEvent(toggleRef, 'click', () => setExpanded(!expanded));
  useNlddEvent(selectRef, 'click', () => onSelect(node.id));
  useNlddEvent(addRef, 'click', () => onAdd(node.id));

  const title = isHistorisch
    ? `Opgeheven per ${node.geldig_tot}`
    : node.bron === 'tooi'
      ? 'Synced uit TOOI-waardelijsten (KOOP/Logius). Read-only.'
      : node.bron === 'synthetisch'
        ? 'Synthetische groep, beheerd door het systeem.'
        : node.bron === 'organogram_scrape'
          ? 'Synced uit rijksoverheid.nl/organogram. Read-only.'
          : undefined;

  return (
    <div>
      {/* Kept as a plain div rather than nldd-list/type="tree": this row is a
          native HTML5 drag-and-drop target for reparenting a person (own
          onDragOver/onDrop), which is independent from and would entangle
          with the tree type's own roving-tabindex keyboard and disclosure
          model. Rows are still list-items built from segments and cells, per
          the fallback the conversion brief calls for when the mapping isn't
          clean. */}
      <div
        style={{
          paddingLeft: `${depth * 16}px`,
          borderRadius: dragOver ? '8px' : undefined,
          boxShadow: dragOver ? '0 0 0 2px var(--primitives-color-accent-500)' : undefined,
          background: dragOver ? 'var(--primitives-color-accent-25)' : undefined,
          opacity: isHistorisch ? 0.6 : undefined,
        }}
        title={title}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <nldd-list-item selected={orUndef(isSelected)} className="group">
          <nldd-list-item-segment
            ref={toggleRef}
            button
            disclosure={hasChildren ? true : undefined}
            expanded={hasChildren ? effectiveExpanded : undefined}
            accessible-label={effectiveExpanded ? 'Inklappen' : 'Uitklappen'}
            className={hasChildren ? undefined : 'invisible'}
          >
            <Icon name="ChevronRight" size="xs" />
          </nldd-list-item-segment>

          <nldd-list-item-segment ref={selectRef} button width="full" accessible-label={node.naam}>
            <nldd-text-cell width="full" color={isHistorisch ? 'secondary' : 'content'}>
              <span className={isHistorisch ? 'line-through' : undefined}>
                {node.afkorting && (
                  <span className="text-text-secondary font-normal mr-1">{node.afkorting}</span>
                )}
                {node.naam}
                {node.manager && (
                  <span className="text-text-secondary font-normal text-xs"> — {node.manager.naam}</span>
                )}
                {(() => {
                  // Synthetische groepen tonen aantal directe children, niet personen
                  if (node.bron === 'synthetisch' && node.children.length > 0) {
                    return (
                      <span className="text-text-secondary font-normal"> ({node.children.length})</span>
                    );
                  }
                  const total = getTotalPersonenCount(node);
                  return total > 0 ? (
                    <span className="text-text-secondary font-normal"> ({total})</span>
                  ) : null;
                })()}
              </span>
            </nldd-text-cell>
          </nldd-list-item-segment>

          {/* Rechter kolom: type-badge rechts uitgelijnd + add-button.
              Geen vaste breedte: de boom staat in een smal paneel, en een
              shrink-0 kolom van 208px liet voor de naam zo weinig over dat die
              per letter afbrak. shrink-0 blijft staan (nldd-container heeft
              geen flex-shrink attribuut), de rest converteert. */}
          <nldd-container layout="row" gap="4" vertical-alignment="center" width="fit-content" className="shrink-0">
            {node.bron === 'fcc_import' && (
              <Badge variant="amber" title="Auto-aangemaakt door FCC-import">
                FCC
              </Badge>
            )}

            <Badge variant={ORGANISATIE_TYPE_BADGE_COLORS[node.type] || 'gray'}>
              {formatOrganisatieType(node.type)}
            </Badge>

            {/* Add child button — niet voor synthetische groepen */}
            {node.bron !== 'synthetisch' ? (
              <nldd-list-item-segment
                ref={addRef}
                button
                accessible-label="Subeenheid toevoegen"
                className="opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <Icon name="Plus" size="xs" />
              </nldd-list-item-segment>
            ) : (
              // Placeholder zodat synth-rijen dezelfde breedte hebben (badges blijven uitgelijnd)
              <span className="h-5 w-5 shrink-0" aria-hidden />
            )}
          </nldd-container>
        </nldd-list-item>
      </div>

      {/* Children */}
      {effectiveExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              selectedId={selectedId}
              onSelect={onSelect}
              onAdd={onAdd}
              onDropPerson={onDropPerson}
              depth={depth + 1}
              searchTerm={searchTerm}
              expandedByDefaultIds={expandedByDefaultIds}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface OrganisatieTreeProps {
  tree: OrganisatieEenheidTreeNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAdd: (parentId: string | null) => void;
  onDropPerson?: (personId: string, targetNodeId: string) => void;
  searchTerm?: string;
  /** Nodes die default open staan. Pad naar eigen organisatie inclusief
   *  ancestors. Recursief doorgegeven aan elke TreeNode. */
  expandedByDefaultIds?: Set<string>;
}

export function OrganisatieTree({ tree, selectedId, onSelect, onAdd, onDropPerson, searchTerm, expandedByDefaultIds }: OrganisatieTreeProps) {
  return (
    <nldd-container gap="2">
      {tree.map((node) => (
        <TreeNode
          key={node.id}
          node={node}
          selectedId={selectedId}
          onSelect={onSelect}
          onAdd={(parentId) => onAdd(parentId)}
          onDropPerson={onDropPerson}
          searchTerm={searchTerm}
          expandedByDefaultIds={expandedByDefaultIds}
        />
      ))}
    </nldd-container>
  );
}
