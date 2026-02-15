import { useState, useCallback, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, LayoutGrid, GitFork, Grid3x3, Search } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { ViewToggle } from '@/components/common/ViewToggle';
import type { ViewToggleOption } from '@/components/common/ViewToggle';
import { Input } from '@/components/common/Input';
import { MultiSelect } from '@/components/common/MultiSelect';
import type { MultiSelectOption } from '@/components/common/MultiSelect';
import { NodeList } from '@/components/nodes/NodeList';
import { NodeCreateForm } from '@/components/nodes/NodeCreateForm';
import { ExportButton } from '@/components/nodes/ExportButton';
import { CorpusGraph } from '@/components/graph/CorpusGraph';
import { CorpusMatrix } from '@/components/graph/CorpusMatrix';
import { NodeType, NODE_TYPE_HEX_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useGraphView } from '@/hooks/useGraph';
import { useDebounce } from '@/hooks/useDebounce';

type ViewMode = 'list' | 'graph' | 'matrix';

const VIEW_OPTIONS: ViewToggleOption<ViewMode>[] = [
  { value: 'list', label: 'Lijst', icon: <LayoutGrid className="h-3.5 w-3.5" /> },
  { value: 'graph', label: 'Netwerk', icon: <GitFork className="h-3.5 w-3.5" /> },
  { value: 'matrix', label: 'Matrix', icon: <Grid3x3 className="h-3.5 w-3.5" /> },
];

const ALL_NODE_TYPES = Object.values(NodeType);

export function CorpusPage() {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get('view');
  const viewMode: ViewMode = viewParam === 'graph' ? 'graph' : viewParam === 'matrix' ? 'matrix' : 'list';
  const { nodeLabel, edgeLabel: vocabEdgeLabel } = useVocabulary();

  // Node type filter: derived from URL, omit param when all selected
  const enabledNodeTypes = useMemo<Set<NodeType>>(() => {
    const typesParam = searchParams.get('types');
    if (!typesParam) return new Set(ALL_NODE_TYPES);
    const parsed = typesParam
      .split(',')
      .filter((t) => ALL_NODE_TYPES.includes(t as NodeType)) as NodeType[];
    return parsed.length > 0 ? new Set(parsed) : new Set(ALL_NODE_TYPES);
  }, [searchParams]);

  // Search: local state for responsive typing, synced to URL via debounce
  const [searchInput, setSearchInput] = useState(() => searchParams.get('q') ?? '');
  const searchQuery = useDebounce(searchInput, 200);

  // Sync URL → local input when URL changes externally (e.g., browser back/forward)
  useEffect(() => {
    const urlQuery = searchParams.get('q') ?? '';
    setSearchInput((prev) => (prev !== urlQuery ? urlQuery : prev));
  }, [searchParams]);

  // Sync debounced search value to URL
  useEffect(() => {
    setSearchParams((prev) => {
      if (searchQuery) prev.set('q', searchQuery); else prev.delete('q');
      return prev;
    }, { replace: true });
  }, [searchQuery, setSearchParams]);

  // Edge type filter state (fetched in graph and matrix modes)
  const { data: graphData, isLoading: isGraphLoading, error: graphError } = useGraphView(undefined, undefined, viewMode === 'graph' || viewMode === 'matrix');

  const availableEdgeTypes = useMemo(() => {
    if (!graphData?.edges) return [];
    const types = new Set<string>();
    for (const edge of graphData.edges) {
      if (edge.edge_type_id) types.add(edge.edge_type_id);
    }
    return [...types].sort();
  }, [graphData?.edges]);

  // Edge type filter: derived from URL, default to all available when param absent
  const enabledEdgeTypes = useMemo<Set<string>>(() => {
    const edgesParam = searchParams.get('edges');
    if (!edgesParam) return new Set(availableEdgeTypes);
    const parsed = edgesParam.split(',').filter((t) => availableEdgeTypes.includes(t));
    return parsed.length > 0 ? new Set(parsed) : new Set(availableEdgeTypes);
  }, [searchParams, availableEdgeTypes]);

  const edgeTypeFilterOptions: MultiSelectOption[] = useMemo(
    () => availableEdgeTypes.map((t) => ({ value: t, label: vocabEdgeLabel(t) })),
    [availableEdgeTypes, vocabEdgeLabel],
  );

  const nodeTypeFilterOptions: MultiSelectOption[] = useMemo(() =>
    ALL_NODE_TYPES.map((t) => ({
      value: t,
      label: nodeLabel(t),
      color: NODE_TYPE_HEX_COLORS[t],
    })),
  [nodeLabel]);

  const handleNodeTypesChange = useCallback((next: Set<string>) => {
    setSearchParams((prev) => {
      const allSelected = ALL_NODE_TYPES.every((t) => next.has(t));
      if (allSelected || next.size === 0) prev.delete('types');
      else prev.set('types', [...next].join(','));
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const handleEdgeTypesChange = useCallback((next: Set<string>) => {
    setSearchParams((prev) => {
      const allSelected = availableEdgeTypes.every((t) => next.has(t));
      if (allSelected || next.size === 0) prev.delete('edges');
      else prev.set('edges', [...next].join(','));
      return prev;
    }, { replace: true });
  }, [setSearchParams, availableEdgeTypes]);

  // Matrix-specific: row and column node type selectors from URL
  const matrixRowType = (searchParams.get('rowType') as NodeType) || NodeType.DOEL;
  const matrixColType = (searchParams.get('colType') as NodeType) || NodeType.INSTRUMENT;

  const setMatrixRowType = useCallback((type: NodeType) => {
    setSearchParams((prev) => {
      prev.set('rowType', type);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const setMatrixColType = useCallback((type: NodeType) => {
    setSearchParams((prev) => {
      prev.set('colType', type);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const setViewMode = useCallback((mode: ViewMode) => {
    setSearchParams((prev) => {
      if (mode === 'list') {
        prev.delete('view');
      } else {
        prev.set('view', mode);
      }
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
          <ViewToggle value={viewMode} onChange={setViewMode} options={VIEW_OPTIONS} />

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
        {viewMode !== 'matrix' && (
          <div className="w-full sm:w-52">
            <MultiSelect
              value={enabledNodeTypes as Set<string>}
              onChange={handleNodeTypesChange}
              options={nodeTypeFilterOptions}
              allLabel="Alle types"
            />
          </div>
        )}
        {(viewMode === 'graph' || viewMode === 'matrix') && edgeTypeFilterOptions.length > 0 && (
          <div className="w-full sm:w-52">
            <MultiSelect
              value={enabledEdgeTypes}
              onChange={handleEdgeTypesChange}
              options={edgeTypeFilterOptions}
              allLabel="Alle relaties"
            />
          </div>
        )}
        {viewMode === 'matrix' && (
          <>
            <select
              value={matrixRowType}
              onChange={(e) => setMatrixRowType(e.target.value as NodeType)}
              className="w-full sm:w-44 rounded-lg border border-border bg-white px-3 py-2 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              aria-label="Rij-type"
            >
              {ALL_NODE_TYPES.map((t) => (
                <option key={t} value={t}>{nodeLabel(t)} (rij)</option>
              ))}
            </select>
            <select
              value={matrixColType}
              onChange={(e) => setMatrixColType(e.target.value as NodeType)}
              className="w-full sm:w-44 rounded-lg border border-border bg-white px-3 py-2 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              aria-label="Kolom-type"
            >
              {ALL_NODE_TYPES.map((t) => (
                <option key={t} value={t}>{nodeLabel(t)} (kolom)</option>
              ))}
            </select>
          </>
        )}
      </div>

      {/* View content */}
      {viewMode === 'list' ? (
        <NodeList enabledNodeTypes={enabledNodeTypes} searchQuery={searchQuery} />
      ) : viewMode === 'graph' ? (
        <CorpusGraph enabledNodeTypes={enabledNodeTypes} searchQuery={searchQuery} enabledEdgeTypes={enabledEdgeTypes} graphData={graphData} isLoading={isGraphLoading} error={graphError} />
      ) : viewMode === 'matrix' ? (
        <CorpusMatrix
          rowNodeType={matrixRowType}
          colNodeType={matrixColType}
          enabledEdgeTypes={enabledEdgeTypes}
          searchQuery={searchQuery}
          graphData={graphData}
          isLoading={isGraphLoading}
          error={graphError}
        />
      ) : null}

      {/* Create form modal */}
      <NodeCreateForm
        open={showCreateForm}
        onClose={() => setShowCreateForm(false)}
      />
    </div>
  );
}
