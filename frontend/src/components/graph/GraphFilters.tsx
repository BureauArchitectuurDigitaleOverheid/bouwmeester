import { NodeType, NODE_TYPE_HEX_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

interface GraphFiltersProps {
  enabledNodeTypes: Set<NodeType>;
  onToggleNodeType: (type: NodeType) => void;
  enabledEdgeTypes: Set<string>;
  availableEdgeTypes: string[];
  onToggleEdgeType: (type: string) => void;
  onSelectAllNodeTypes: () => void;
  onDeselectAllNodeTypes: () => void;
}

export function GraphFilters({
  enabledNodeTypes,
  onToggleNodeType,
  enabledEdgeTypes,
  availableEdgeTypes,
  onToggleEdgeType,
  onSelectAllNodeTypes,
  onDeselectAllNodeTypes,
}: GraphFiltersProps) {
  const { nodeLabel, edgeLabel } = useVocabulary();
  const allNodeTypesSelected = enabledNodeTypes.size === Object.values(NodeType).length;

  return (
    <div className="bg-white rounded-xl border border-border p-4 space-y-4 shadow-sm">
      {/* Node type filters */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            Node types
          </h3>
          <button
            onClick={allNodeTypesSelected ? onDeselectAllNodeTypes : onSelectAllNodeTypes}
            className="text-xs text-primary-600 hover:text-primary-800 font-medium"
          >
            {allNodeTypesSelected ? 'Geen' : 'Alles'}
          </button>
        </div>
        <div className="space-y-1.5">
          {Object.values(NodeType).map((type) => {
            const color = NODE_TYPE_HEX_COLORS[type] ?? '#9ca3af';
            return (
              <label
                key={type}
                className="flex items-center gap-2 cursor-pointer group"
              >
                <input
                  type="checkbox"
                  checked={enabledNodeTypes.has(type)}
                  onChange={() => onToggleNodeType(type)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500 h-3.5 w-3.5"
                />
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ background: color }}
                />
                <span className="text-sm text-text group-hover:text-primary-700">
                  {nodeLabel(type)}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      {/* Edge type filters */}
      {availableEdgeTypes.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
            Relatie types
          </h3>
          <div className="space-y-1.5">
            {availableEdgeTypes.map((edgeType) => (
              <label
                key={edgeType}
                className="flex items-center gap-2 cursor-pointer group"
              >
                <input
                  type="checkbox"
                  checked={enabledEdgeTypes.has(edgeType)}
                  onChange={() => onToggleEdgeType(edgeType)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500 h-3.5 w-3.5"
                />
                <span className="text-sm text-text group-hover:text-primary-700">
                  {edgeLabel(edgeType)}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
