import { useEffect, useRef, useState } from 'react';
import { Badge } from '@/components/common/Badge';
import { Icon } from '@/components/nldd/Icon';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import type { OrganisatieEenheidTreeNode } from '@/types';
import { formatOrganisatieType } from '@/types';

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

  // Manager and headcount, on the cell's supporting line. A synthetic group
  // has no people of its own, so there the count is of the units under it.
  const count =
    node.bron === 'synthetisch' ? node.children.length : getTotalPersonenCount(node);
  const supportingText = [
    node.manager?.naam,
    count > 0 ? `${count} ${node.bron === 'synthetisch' ? 'onderdelen' : 'personen'}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

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
          model. Rows are still list-items built from segments and cells. */}
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
        {/* The open/closed state belongs on the row: `disclosure` makes the
            segment take its aria-expanded from there, and an `expanded` set on
            the segment itself is ignored.

            An open row announces itself; a collapsed one does not. The row
            only relays a `false` downward when it renders the children through
            its own `children` slot, and this tree keeps them in the div above,
            which is the drag-and-drop target. Setting aria-expanded on the row
            as well puts the state in two places that disagree, so the
            accessible label carries it in words instead. */}
        <nldd-list-item
          selected={orUndef(isSelected)}
          {...(hasChildren ? { expanded: effectiveExpanded } : {})}
          className="group"
        >
          <nldd-list-item-segment
            ref={toggleRef}
            button
            disclosure={orUndef(hasChildren)}
            accessible-label={effectiveExpanded ? 'Inklappen' : 'Uitklappen'}
            // 'invisible' keeps the segment's width reserved so leaf rows
            // align with rows that do have a disclosure chevron; no
            // nldd-list-item-segment prop hides while preserving layout.
            className={hasChildren ? undefined : 'invisible'}
          >
            <Icon name="ChevronRight" size="xs" />
          </nldd-list-item-segment>

          {/* `min-width: 0` is what lets this segment give way. Without it a
              flex item refuses to shrink below its content, so the name
              claimed the full row and the badges beside it were pushed off
              the right edge of the card. */}
          <nldd-list-item-segment
            ref={selectRef}
            button
            width="full"
            accessible-label={node.naam}
            style={{ minWidth: 0, flex: '1 1 auto' }}
          >
            {/* The name goes in `text`, the rest in `supporting-text`, rather
                than one line of hand-styled spans. Three reasons:

                The cell keeps its content inside its own box; a span does not.
                The old markup put `.truncate` on an inline <span>, where
                `overflow` has no effect at all, so a long ministry name grew
                past its own segment and ran underneath the type tag to its
                right. The cell wraps to a second line instead (its own
                `overflow-wrap: anywhere`, with no opt-out), which for a name
                like "ministerie van Landbouw, Visserij, Voedselzekerheid en
                Natuur" is the better answer anyway: an ellipsis there cuts off
                the part that distinguishes it.

                It also separates the name from what is only about the name. A
                manager and a headcount read as part of the title when they sit
                on the same line in the same size; on the supporting line they
                are what they are.

                And `query` lets the cell mark the search term, instead of
                leaving the user to find it in a list that is open at every
                level while a search is running. The mode has to be `match`:
                the default is `predictive`, which bolds everything the query
                did NOT match, because it is meant for an autocomplete showing
                what is left to type. In a filter that reads as the opposite of
                the truth. */}
            <nldd-text-cell
              width="full"
              color={isHistorisch ? 'secondary' : 'content'}
              text={node.afkorting ? `${node.afkorting} ${node.naam}` : node.naam}
              {...(supportingText ? { 'supporting-text': supportingText } : {})}
              {...(searchTerm.trim()
                ? { query: searchTerm.trim(), 'query-mark-mode': 'match' }
                : {})}
              style={isHistorisch ? { textDecoration: 'line-through' } : undefined}
            />
          </nldd-list-item-segment>

          {/* Right-hand items sit directly in the row, not in a wrapper.
              An nldd-container here measured zero pixels wide and its badges
              rendered outside it, past the card's right edge: the host is
              display:block, so `width: auto` resolves against a parent that
              allotted it nothing, and the inner flex never reports an
              intrinsic width back up. The list item is itself a flex row, so
              these belong in it as their own items.

              FCC keeps its color: it marks the few rows that an import created
              rather than a person, and that is an exception worth seeing. */}
          {node.bron === 'fcc_import' && (
            <Badge variant="amber" title="Auto-aangemaakt door FCC-import" className="row-badge-first-line">
              FCC
            </Badge>
          )}

          {/* The type reads neutral, not in a color per type. The tree already
              carries the hierarchy in its indentation, so a filled color block
              on every row competed with the names for both attention and
              width while saying what the position in the tree had said
              already. Neutral keeps it readable as a label without it being
              the loudest thing in the row. */}
          <Badge variant="gray" className="row-badge-first-line">
            {formatOrganisatieType(node.type)}
          </Badge>

          {/* Add child button — niet voor synthetische groepen */}
          {node.bron !== 'synthetisch' ? (
            <nldd-list-item-segment
              ref={addRef}
              button
              accessible-label="Subeenheid toevoegen"
              // group/group-hover reveal-on-row-hover has no nldd
              // equivalent; `group` itself lives on the parent
              // nldd-list-item above. group-hover-reveal is the real CSS
              // backing this in utilities.css.
              className="group-hover-reveal"
            >
              <Icon name="Plus" size="xs" />
            </nldd-list-item-segment>
          ) : (
            // Placeholder zodat synth-rijen dezelfde breedte hebben (badges blijven uitgelijnd)
            <nldd-spacer size="20" aria-hidden />
          )}
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
