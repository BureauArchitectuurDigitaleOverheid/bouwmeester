import { useEffect, useState } from 'react';
import { ChevronRight, ChevronDown, Plus } from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';
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

  return (
    <div>
      <div
        className={clsx(
          'group flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer transition-colors text-sm',
          isSelected
            ? 'bg-primary-50 text-primary-700 font-medium'
            : 'text-text hover:bg-gray-50',
          dragOver && 'ring-2 ring-primary-500 bg-primary-50/50',
          isHistorisch && 'text-text-secondary line-through opacity-60',
        )}
        title={
          isHistorisch
            ? `Opgeheven per ${node.geldig_tot}`
            : node.bron === 'tooi'
              ? 'Synced uit TOOI-waardelijsten (KOOP/Logius). Read-only.'
              : node.bron === 'synthetisch'
                ? 'Synthetische groep, beheerd door het systeem.'
                : node.bron === 'organogram_scrape'
                  ? 'Synced uit rijksoverheid.nl/organogram. Read-only.'
                  : undefined
        }
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelect(node.id)}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Expand toggle */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(!expanded);
          }}
          className={clsx(
            'flex items-center justify-center h-5 w-5 rounded shrink-0 transition-colors',
            hasChildren ? 'hover:bg-gray-200' : 'invisible',
          )}
        >
          {hasChildren &&
            (effectiveExpanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            ))}
        </button>

        {/* Name + afkorting + manager + total person count */}
        <span className="truncate flex-1">
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

        {/* Vaste rechter-kolom: type-badge rechts uitgelijnd + add-button. */}
        <div className="flex items-center gap-1 shrink-0 w-52 justify-end">
          {node.bron === 'fcc_import' && (
            <Badge
              variant="amber"
              className="text-[10px] px-1.5 py-0 shrink-0"
              title="Auto-aangemaakt door FCC-import"
            >
              FCC
            </Badge>
          )}

          <Badge
            variant={ORGANISATIE_TYPE_BADGE_COLORS[node.type] || 'gray'}
            className="text-xs px-2 py-0.5 shrink-0"
          >
            {formatOrganisatieType(node.type)}
          </Badge>

          {/* Add child button — niet voor synthetische groepen */}
          {node.bron !== 'synthetisch' ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onAdd(node.id);
              }}
              className="opacity-0 group-hover:opacity-100 flex items-center justify-center h-5 w-5 rounded hover:bg-gray-200 shrink-0 transition-opacity"
              title="Subeenheid toevoegen"
            >
              <Plus className="h-3 w-3" />
            </button>
          ) : (
            // Placeholder zodat synth-rijen dezelfde breedte hebben (badges blijven uitgelijnd)
            <span className="h-5 w-5 shrink-0" aria-hidden />
          )}
        </div>
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
    <div className="space-y-0.5">
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
    </div>
  );
}
