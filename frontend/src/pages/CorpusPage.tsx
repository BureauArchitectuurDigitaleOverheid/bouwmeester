import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, LayoutGrid, GitFork, Search } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { MultiSelect } from '@/components/common/MultiSelect';
import type { MultiSelectOption } from '@/components/common/MultiSelect';
import { NodeList } from '@/components/nodes/NodeList';
import { NodeCreateForm } from '@/components/nodes/NodeCreateForm';
import { ExportButton } from '@/components/nodes/ExportButton';
import { CorpusGraph } from '@/components/graph/CorpusGraph';
import { NodeType, NODE_TYPE_HEX_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useGraphView } from '@/hooks/useGraph';
import { useDebounce } from '@/hooks/useDebounce';

type ViewMode = 'list' | 'graph';

export function CorpusPage() {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const viewMode: ViewMode = searchParams.get('view') === 'graph' ? 'graph' : 'list';
  const { nodeLabel, edgeLabel: vocabEdgeLabel } = useVocabulary();

  // Shared filter state
  const [enabledNodeTypes, setEnabledNodeTypes] = useState<Set<NodeType>>(
    () => new Set(Object.values(NodeType)),
  );
  const [searchInput, setSearchInput] = useState('');
  const searchQuery = useDebounce(searchInput, 200);

  // Edge type filter state (graph-specific, only fetched in graph mode)
  const { data: graphData } = useGraphView(undefined, undefined, viewMode === 'graph');
  const [enabledEdgeTypes, setEnabledEdgeTypes] = useState<Set<string>>(new Set());
  const prevAvailableRef = useRef<string>('');

  const availableEdgeTypes = useMemo(() => {
    if (!graphData?.edges) return [];
    const types = new Set<string>();
    for (const edge of graphData.edges) {
      if (edge.edge_type_id) types.add(edge.edge_type_id);
    }
    return [...types].sort();
  }, [graphData?.edges]);

  // Auto-enable new edge types when available set changes
  useEffect(() => {
    const key = availableEdgeTypes.join(',');
    if (key && key !== prevAvailableRef.current) {
      setEnabledEdgeTypes(new Set(availableEdgeTypes));
      prevAvailableRef.current = key;
    }
  }, [availableEdgeTypes]);

  const edgeTypeFilterOptions: MultiSelectOption[] = useMemo(
    () => availableEdgeTypes.map((t) => ({ value: t, label: vocabEdgeLabel(t) })),
    [availableEdgeTypes, vocabEdgeLabel],
  );

  const nodeTypeFilterOptions: MultiSelectOption[] = useMemo(() =>
    Object.values(NodeType).map((t) => ({
      value: t,
      label: nodeLabel(t),
      color: NODE_TYPE_HEX_COLORS[t],
    })),
  [nodeLabel]);

  const handleNodeTypesChange = useCallback((next: Set<string>) => {
    setEnabledNodeTypes(next as Set<NodeType>);
  }, []);

  const setViewMode = useCallback((mode: ViewMode) => {
    setSearchParams((prev) => {
      if (mode === 'graph') prev.set('view', 'graph'); else prev.delete('view');
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-sm text-text-secondary">
            Bekijk en beheer alle beleidsdocumenten, dossiers en instrumenten.
          </p>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* View mode toggle */}
          <div className="flex items-center bg-gray-100 rounded-xl p-0.5">
            <button
              onClick={() => setViewMode('list')}
              className={clsx(
                'flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-150',
                viewMode === 'list'
                  ? 'bg-white text-text shadow-sm'
                  : 'text-text-secondary hover:text-text',
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Lijst</span>
            </button>
            <button
              onClick={() => setViewMode('graph')}
              className={clsx(
                'flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-150',
                viewMode === 'graph'
                  ? 'bg-white text-text shadow-sm'
                  : 'text-text-secondary hover:text-text',
              )}
            >
              <GitFork className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Netwerk</span>
            </button>
          </div>

          <ExportButton hideLabel />

          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowCreateForm(true)}
          >
            <span className="hidden sm:inline">Nieuwe node</span>
          </Button>
        </div>
      </div>

      {/* Shared filter bar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
        <div className="relative w-full sm:w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Zoek in corpus..."
            className="pl-9"
          />
        </div>
        <div className="w-full sm:w-52">
          <MultiSelect
            value={enabledNodeTypes as Set<string>}
            onChange={handleNodeTypesChange}
            options={nodeTypeFilterOptions}
            allLabel="Alle types"
          />
        </div>
        {viewMode === 'graph' && edgeTypeFilterOptions.length > 0 && (
          <div className="w-full sm:w-52">
            <MultiSelect
              value={enabledEdgeTypes}
              onChange={setEnabledEdgeTypes}
              options={edgeTypeFilterOptions}
              allLabel="Alle relaties"
            />
          </div>
        )}
      </div>

      {/* View content */}
      {viewMode === 'list'
        ? <NodeList enabledNodeTypes={enabledNodeTypes} searchQuery={searchQuery} />
        : <CorpusGraph enabledNodeTypes={enabledNodeTypes} searchQuery={searchQuery} enabledEdgeTypes={enabledEdgeTypes} />
      }

      {/* Create form modal */}
      <NodeCreateForm
        open={showCreateForm}
        onClose={() => setShowCreateForm(false)}
      />
    </div>
  );
}
