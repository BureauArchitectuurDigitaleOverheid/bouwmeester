import { useState } from 'react';
import { ChevronRight, ChevronDown, Plus } from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/common/Badge';
import type { OrganisatieEenheidTreeNode } from '@/types';
import { ORGANISATIE_TYPE_LABELS } from '@/types';

function getTotalPersonenCount(node: OrganisatieEenheidTreeNode): number {
  return node.personen_count + node.children.reduce((sum, child) => sum + getTotalPersonenCount(child), 0);
}

const TYPE_BADGE_COLORS: Record<string, 'blue' | 'purple' | 'amber' | 'cyan' | 'green' | 'gray'> = {
  ministerie: 'blue',
  directoraat_generaal: 'purple',
  directie: 'amber',
  afdeling: 'cyan',
  team: 'green',
};

interface TreeNodeProps {
  node: OrganisatieEenheidTreeNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onAdd: (parentId: string) => void;
  onDropPerson?: (personId: string, targetNodeId: string) => void;
  depth?: number;
}

function TreeNode({ node, selectedId, onSelect, onAdd, onDropPerson, depth = 0 }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(depth < 2);
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
        )}
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
            (expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            ))}
        </button>

        {/* Name + manager + total person count */}
        <span className="truncate flex-1">
          {node.naam}
          {node.manager && (
            <span className="text-text-secondary font-normal text-xs"> — {node.manager.naam}</span>
          )}
          {(() => {
            const total = getTotalPersonenCount(node);
            return total > 0 ? (
              <span className="text-text-secondary font-normal"> ({total})</span>
            ) : null;
          })()}
        </span>

        <Badge
          variant={TYPE_BADGE_COLORS[node.type] || 'gray'}
          className="text-[10px] px-1.5 py-0"
        >
          {ORGANISATIE_TYPE_LABELS[node.type] || node.type}
        </Badge>

        {/* Add child button */}
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
      </div>

      {/* Children */}
      {expanded && hasChildren && (
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
}

export function OrganisatieTree({ tree, selectedId, onSelect, onAdd, onDropPerson }: OrganisatieTreeProps) {
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
        />
      ))}
    </div>
  );
}
