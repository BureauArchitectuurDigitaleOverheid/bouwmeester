import { useState, useEffect, useMemo } from 'react';
import { useOrganisatieTree } from '@/hooks/useOrganisatie';
import { ORGANISATIE_TYPE_LABELS } from '@/types';
import type { OrganisatieEenheidTreeNode } from '@/types';

interface CascadingOrgSelectProps {
  value: string;
  onChange: (id: string) => void;
  label?: string;
}

/**
 * Find the path of node IDs from root to a target node in the tree.
 * Returns an array of IDs: [rootId, childId, ..., targetId].
 */
function findPathToNode(
  nodes: OrganisatieEenheidTreeNode[],
  targetId: string,
): string[] {
  for (const node of nodes) {
    if (node.id === targetId) return [node.id];
    if (node.children.length > 0) {
      const childPath = findPathToNode(node.children, targetId);
      if (childPath.length > 0) return [node.id, ...childPath];
    }
  }
  return [];
}

export function CascadingOrgSelect({
  value,
  onChange,
  label = 'Organisatie-eenheid',
}: CascadingOrgSelectProps) {
  const { data: tree = [], isLoading } = useOrganisatieTree();
  const [selections, setSelections] = useState<string[]>([]);

  // When value changes externally (or on mount), rebuild the path
  useEffect(() => {
    setSelections((prev) => {
      if (!value || tree.length === 0) {
        return prev.length === 0 ? prev : [];
      }
      const path = findPathToNode(tree, value);
      if (path.length === 0) return prev;
      // Only update if the path actually changed
      if (
        prev.length === path.length &&
        prev.every((s, i) => s === path[i])
      ) {
        return prev;
      }
      return path;
    });
  }, [value, tree]);

  // Build levels: each level has options and a selected value
  const levels = useMemo(() => {
    const result: {
      options: OrganisatieEenheidTreeNode[];
      selected: string;
      type: string;
    }[] = [];
    let currentNodes = tree;

    for (const sel of selections) {
      const typeLabel =
        currentNodes.length > 0
          ? ORGANISATIE_TYPE_LABELS[currentNodes[0].type] || ''
          : '';
      result.push({ options: currentNodes, selected: sel, type: typeLabel });
      const node = currentNodes.find((n) => n.id === sel);
      currentNodes = node?.children || [];
    }

    // Add the next empty level if there are children to pick from
    if (currentNodes.length > 0) {
      const typeLabel = ORGANISATIE_TYPE_LABELS[currentNodes[0].type] || '';
      result.push({ options: currentNodes, selected: '', type: typeLabel });
    }

    return result;
  }, [tree, selections]);

  const handleChange = (levelIndex: number, nodeId: string) => {
    const newSelections = selections.slice(0, levelIndex);
    if (nodeId) {
      newSelections.push(nodeId);
    }
    setSelections(newSelections);
    // The deepest selected node is the value
    onChange(newSelections.length > 0 ? newSelections[newSelections.length - 1] : '');
  };

  if (isLoading) {
    return (
      <div>
        {label && (
          <label className="block text-sm font-medium text-text mb-1">
            {label}
          </label>
        )}
        <p className="text-xs text-text-secondary py-2">Laden...</p>
      </div>
    );
  }

  if (tree.length === 0) return null;

  return (
    <div>
      {label && (
        <label className="block text-sm font-medium text-text mb-1">
          {label}
        </label>
      )}
      <div className="space-y-2">
        {levels.map((level, i) => (
          <select
            key={`${i}-${level.type}`}
            value={level.selected}
            onChange={(e) => handleChange(i, e.target.value)}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm text-text bg-white focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          >
            <option value="">
              {level.type
                ? `Kies ${level.type.toLowerCase()}...`
                : 'Kies eenheid...'}
            </option>
            {level.options.map((node) => (
              <option key={node.id} value={node.id}>
                {node.naam}
              </option>
            ))}
          </select>
        ))}
      </div>
    </div>
  );
}
