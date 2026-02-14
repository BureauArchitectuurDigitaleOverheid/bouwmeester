import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { ChevronDown, ChevronUp, Check, X, ExternalLink, Users, Calendar, Plus, Trash2, Link, Undo2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import type { SelectOption } from '@/components/common/CreatableSelect';
import {
  useApproveSuggestedEdge,
  useRejectSuggestedEdge,
  useResetSuggestedEdge,
  useUpdateSuggestedEdge,
  useRejectParlementairItem,
  useReopenParlementairItem,
  useCompleteParlementairReview,
} from '@/hooks/useParlementair';
import { useCreateEdge, useDeleteEdge } from '@/hooks/useEdges';
import { useQuery, useQueries } from '@tanstack/react-query';
import { getEdges } from '@/api/edges';
import { getNodeStakeholders } from '@/api/nodes';
import { useNodes, useCreateNode } from '@/hooks/useNodes';
import { usePeople } from '@/hooks/usePeople';
import { useTags, useNodeTags, useAddTagToNode, useRemoveTagFromNode } from '@/hooks/useTags';
import type { ParlementairItem } from '@/types';
import { NodeType } from '@/types';
import {
  PARLEMENTAIR_ITEM_STATUS_LABELS,
  PARLEMENTAIR_ITEM_STATUS_COLORS,
  PARLEMENTAIR_TYPE_LABELS,
  PARLEMENTAIR_TYPE_COLORS,
  NODE_TYPE_COLORS,
  formatFunctie,
} from '@/types';
import { NodeDetailModal } from '@/components/nodes/NodeDetailModal';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { EDGE_TYPE_VOCABULARY } from '@/vocabulary';
import { formatDateLong } from '@/utils/dates';
import type { CompleteReviewData } from '@/api/parlementair';

interface FollowUpTaskRow {
  title: string;
  assignee_id: string;
  deadline: string;
}

interface ParlementairReviewCardProps {
  item: ParlementairItem;
  defaultExpanded?: boolean;
}

export function ParlementairReviewCard({ item, defaultExpanded = false }: ParlementairReviewCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [eigenaarId, setEigenaarId] = useState('');
  const [followUpTasks, setFollowUpTasks] = useState<FollowUpTaskRow[]>([]);
  const [showAddEdge, setShowAddEdge] = useState(false);
  const [newEdgeTargetId, setNewEdgeTargetId] = useState('');
  const [newEdgeTypeId, setNewEdgeTypeId] = useState('');
  const [tagInput, setTagInput] = useState('');
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [modalNodeId, setModalNodeId] = useState<string | null>(null);
  const [tagHighlightIdx, setTagHighlightIdx] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);
  const tagContainerRef = useRef<HTMLDivElement>(null);
  const tagInputRef = useRef<HTMLInputElement>(null);
  const tagListRef = useRef<HTMLUListElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (defaultExpanded && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [defaultExpanded]);

  const { nodeLabel, edgeLabel } = useVocabulary();
  const approveEdge = useApproveSuggestedEdge();
  const rejectEdge = useRejectSuggestedEdge();
  const resetEdge = useResetSuggestedEdge();
  const updateSuggestedEdge = useUpdateSuggestedEdge();
  const rejectItem = useRejectParlementairItem();
  const reopenItem = useReopenParlementairItem();
  const completeReview = useCompleteParlementairReview();
  const createEdge = useCreateEdge();
  const deleteEdge = useDeleteEdge();
  const createNode = useCreateNode();
  const { data: people } = usePeople();
  const { data: allNodes } = useNodes();
  const { data: allTags } = useTags();
  const { data: nodeTags } = useNodeTags(item.corpus_node_id ?? '');
  const addTag = useAddTagToNode();
  const removeTag = useRemoveTagFromNode();

  const corpusNodeId = item.corpus_node_id;
  const { data: nodeEdges } = useQuery({
    queryKey: ['edges', { node_id: corpusNodeId }],
    queryFn: () => getEdges({ node_id: corpusNodeId! }),
    enabled: !!corpusNodeId,
  });

  // Fetch stakeholders for the corpus node and all connected nodes
  const uniqueNodeIds = useMemo(() => {
    if (!corpusNodeId) return [];
    const ids = [corpusNodeId, ...(nodeEdges ?? []).map((e) =>
      e.from_node_id === corpusNodeId ? e.to_node_id : e.from_node_id,
    )];
    return [...new Set(ids)];
  }, [corpusNodeId, nodeEdges]);
  const stakeholderQueries = useQueries({
    queries: uniqueNodeIds.map((nodeId) => ({
      queryKey: ['node-stakeholders', nodeId],
      queryFn: () => getNodeStakeholders(nodeId),
    })),
  });
  const relevantPersonIds = new Set(
    stakeholderQueries
      .flatMap((q) => q.data ?? [])
      .filter((s) => s.rol === 'eigenaar')
      .map((s) => s.person.id),
  );

  // Helper for functie display
  const functieLabel = formatFunctie;

  // People options sorted: relevant eigenaren first, then the rest
  const sortedPeopleOptions: SelectOption[] = (people ?? [])
    .map((p) => ({
      value: p.id,
      label: p.naam,
      description: functieLabel(p.functie),
      _relevant: relevantPersonIds.has(p.id),
    }))
    .sort((a, b) => {
      if (a._relevant !== b._relevant) return a._relevant ? -1 : 1;
      return a.label.localeCompare(b.label);
    })
    .map(({ _relevant, ...rest }) => rest);

  // Edge type options
  const edgeTypeOptions: SelectOption[] = Object.keys(EDGE_TYPE_VOCABULARY).map((key) => ({
    value: key,
    label: edgeLabel(key),
  }));

  // Target node options for new edges
  const targetOptions: SelectOption[] = (allNodes ?? [])
    .filter((n) => n.id !== corpusNodeId)
    .map((n) => ({
      value: n.id,
      label: n.title,
      description: nodeLabel(n.node_type),
    }));

  const handleCreateNode = useCallback(
    async (text: string): Promise<string | null> => {
      const node = await createNode.mutateAsync({
        title: text,
        node_type: NodeType.NOTITIE,
      });
      return node.id;
    },
    [createNode],
  );

  // Tag search logic
  const existingTagIds = new Set((nodeTags ?? []).map((nt) => nt.tag.id));
  const debouncedQuery = tagInput.trim().toLowerCase();
  const tagSearchResults = (allTags ?? []).filter(
    (t) => !existingTagIds.has(t.id) && t.name.toLowerCase().includes(debouncedQuery),
  ).slice(0, 10);
  const showCreateTag = debouncedQuery.length > 0 &&
    !tagSearchResults.some((t) => t.name.toLowerCase() === debouncedQuery);
  const tagTotalItems = tagSearchResults.length + (showCreateTag ? 1 : 0);

  useEffect(() => { setTagHighlightIdx(0); }, [tagInput]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (tagContainerRef.current && !tagContainerRef.current.contains(e.target as Node)) {
        setTagDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (tagDropdownOpen && tagListRef.current) {
      const el = tagListRef.current.children[tagHighlightIdx] as HTMLElement | undefined;
      el?.scrollIntoView({ block: 'nearest' });
    }
  }, [tagHighlightIdx, tagDropdownOpen]);

  const handleSelectTag = useCallback((tagId: string) => {
    if (!corpusNodeId) return;
    addTag.mutate({ nodeId: corpusNodeId, data: { tag_id: tagId } });
    setTagInput('');
    setTagDropdownOpen(false);
  }, [addTag, corpusNodeId]);

  const handleCreateTag = useCallback(() => {
    if (!tagInput.trim() || !corpusNodeId) return;
    addTag.mutate({ nodeId: corpusNodeId, data: { tag_name: tagInput.trim() } });
    setTagInput('');
    setTagDropdownOpen(false);
  }, [addTag, corpusNodeId, tagInput]);

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (!tagDropdownOpen) {
      if (tagInput.trim() && (e.key === 'ArrowDown' || e.key === 'Enter')) {
        setTagDropdownOpen(true);
        e.preventDefault();
      }
      return;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        if (tagTotalItems > 0) setTagHighlightIdx((i) => (i + 1) % tagTotalItems);
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (tagTotalItems > 0) setTagHighlightIdx((i) => (i - 1 + tagTotalItems) % tagTotalItems);
        break;
      case 'Enter':
        e.preventDefault();
        if (showCreateTag && tagHighlightIdx === tagSearchResults.length) {
          handleCreateTag();
        } else if (tagSearchResults[tagHighlightIdx]) {
          handleSelectTag(tagSearchResults[tagHighlightIdx].id);
        }
        break;
      case 'Escape':
        setTagDropdownOpen(false);
        break;
    }
  };

  const handleCompleteSubmit = () => {
    const data: CompleteReviewData = {
      eigenaar_id: eigenaarId,
      tasks: followUpTasks
        .filter((t) => t.title.trim())
        .map((t) => ({
          title: t.title,
          assignee_id: t.assignee_id || undefined,
          deadline: t.deadline || undefined,
        })),
    };
    completeReview.mutate(
      { id: item.id, data },
      {
        onSuccess: () => {
          setEigenaarId('');
          setFollowUpTasks([]);
        },
      },
    );
  };

  const handleAddEdge = async () => {
    if (!corpusNodeId || !newEdgeTargetId || !newEdgeTypeId) return;
    try {
      await createEdge.mutateAsync({
        from_node_id: corpusNodeId,
        to_node_id: newEdgeTargetId,
        edge_type_id: newEdgeTypeId,
      });
      setNewEdgeTargetId('');
      setNewEdgeTypeId('');
      setShowAddEdge(false);
    } catch {
      // Error already handled by useMutationWithError
    }
  };

  const addTaskRow = () => {
    setFollowUpTasks([...followUpTasks, { title: '', assignee_id: '', deadline: '' }]);
  };

  const updateTaskRow = (index: number, field: keyof FollowUpTaskRow, value: string) => {
    setFollowUpTasks(followUpTasks.map((t, i) => (i === index ? { ...t, [field]: value } : t)));
  };

  const removeTaskRow = (index: number) => {
    setFollowUpTasks(followUpTasks.filter((_, i) => i !== index));
  };

  // Sort suggested edges: confidence desc, then node type alphabetically
  const sortedSuggestedEdges = [...(item.suggested_edges ?? [])].sort((a, b) => {
    if (b.confidence !== a.confidence) return b.confidence - a.confidence;
    const typeA = a.target_node?.node_type ?? '';
    const typeB = b.target_node?.node_type ?? '';
    return typeA.localeCompare(typeB);
  });

  const pendingEdges = sortedSuggestedEdges.filter((e) => e.status === 'pending');

  // Edges manually added (not from suggested edges)
  const suggestedEdgeIds = new Set(
    (item.suggested_edges ?? []).filter((se) => se.edge_id).map((se) => se.edge_id),
  );
  const suggestedTargetNodeIds = new Set(
    (item.suggested_edges ?? []).map((se) => se.target_node_id),
  );
  const manualEdges = (nodeEdges ?? []).filter(
    (e) => !suggestedEdgeIds.has(e.id) && !suggestedTargetNodeIds.has(
      e.from_node_id === corpusNodeId ? e.to_node_id : e.from_node_id,
    ),
  ).sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

  const typeLabel = PARLEMENTAIR_TYPE_LABELS[item.type] ?? item.type;
  const typeColor = PARLEMENTAIR_TYPE_COLORS[item.type] ?? 'gray';

  return (
    <div ref={cardRef}>
    <Card>
      {/* Clickable header */}
      <div
        className="flex items-start justify-between gap-3 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Badge variant={typeColor}>
              {typeLabel}
            </Badge>
            <Badge
              variant={PARLEMENTAIR_ITEM_STATUS_COLORS[item.status]}
            >
              {PARLEMENTAIR_ITEM_STATUS_LABELS[item.status]}
            </Badge>
            <span className="text-xs text-text-secondary">{item.bron === 'tweede_kamer' ? 'Tweede Kamer' : 'Eerste Kamer'}</span>
            <span className="text-xs text-text-secondary">{item.zaak_nummer}</span>
            {item.datum && (
              <span className="text-xs text-text-secondary flex items-center gap-0.5">
                <Calendar className="h-3 w-3" />
                {formatDateLong(item.datum)}
              </span>
            )}
            {item.deadline && (
              <span className="text-xs text-orange-600 flex items-center gap-0.5">
                <Calendar className="h-3 w-3" />
                Deadline: {formatDateLong(item.deadline)}
              </span>
            )}
            {item.ministerie && (
              <span className="text-xs text-text-secondary">{item.ministerie}</span>
            )}
          </div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-text">{item.onderwerp}</h3>
            {item.document_url && (
              <a
                href={item.document_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-600 hover:text-primary-700 shrink-0"
                title="Bekijk op tweedekamer.nl"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
          <p className="text-xs text-text-secondary">Zaak: {item.titel}</p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {item.suggested_edges && item.suggested_edges.length > 0 && (
            <span className="text-xs text-text-secondary">
              {pendingEdges.length} te beoordelen
            </span>
          )}
          <div className="p-1 rounded hover:bg-gray-100 transition-colors">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border space-y-5">
          {/* Quick links bar */}
          <div className="flex items-center gap-3">
            {item.corpus_node_id && (
              <button
                onClick={() => navigate(`/nodes/${item.corpus_node_id}`)}
                className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1 transition-colors"
              >
                <ExternalLink className="h-3 w-3" />
                Bekijk node
              </button>
            )}
            {item.document_url && (
              <a
                href={item.document_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1 transition-colors"
              >
                <ExternalLink className="h-3 w-3" />
                Bekijk op tweedekamer.nl
              </a>
            )}
          </div>

          {/* Indieners */}
          {item.indieners && item.indieners.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1.5 flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                Indieners
              </h4>
              <div className="flex flex-wrap gap-1">
                {item.indieners.map((indiener) => (
                  <Badge key={indiener} variant="purple">{indiener}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Summary */}
          {item.llm_samenvatting && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1">Samenvatting</h4>
              <p className="text-sm text-text-secondary">{item.llm_samenvatting}</p>
            </div>
          )}

          {/* Document text */}
          {item.document_tekst && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1">Tekst</h4>
              <p className="text-sm text-text-secondary whitespace-pre-wrap bg-gray-50 rounded-lg p-3 max-h-48 overflow-y-auto">
                {item.document_tekst}
              </p>
            </div>
          )}

          {/* Matched tags */}
          {item.matched_tags && item.matched_tags.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1.5">Gematchte tags</h4>
              <div className="flex flex-wrap gap-1">
                {item.matched_tags.map((tag) => (
                  <Badge key={tag} variant="slate">{tag}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Tags on corpus node */}
          {corpusNodeId && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1.5">Tags</h4>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {nodeTags?.map((nt) => (
                  <span
                    key={nt.id}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 text-xs font-medium"
                  >
                    {nt.tag.name}
                    <button
                      onClick={() => removeTag.mutate({ nodeId: corpusNodeId, tagId: nt.tag.id })}
                      className="hover:text-red-500 transition-colors ml-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                {(!nodeTags || nodeTags.length === 0) && (
                  <span className="text-xs text-text-secondary">Geen tags</span>
                )}
              </div>
              <div className="relative max-w-xs" ref={tagContainerRef}>
                <input
                  ref={tagInputRef}
                  type="text"
                  value={tagInput}
                  onChange={(e) => {
                    setTagInput(e.target.value);
                    if (e.target.value.trim()) setTagDropdownOpen(true);
                    else setTagDropdownOpen(false);
                  }}
                  onFocus={() => { if (tagInput.trim()) setTagDropdownOpen(true); }}
                  onKeyDown={handleTagKeyDown}
                  placeholder="Tag zoeken of toevoegen..."
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                />
                {tagDropdownOpen && tagTotalItems > 0 && (
                  <ul
                    ref={tagListRef}
                    className="absolute z-50 mt-1 w-full max-h-48 overflow-auto rounded-xl border border-border bg-white shadow-lg py-1"
                  >
                    {tagSearchResults.map((tag, idx) => (
                      <li
                        key={tag.id}
                        onClick={() => handleSelectTag(tag.id)}
                        onMouseEnter={() => setTagHighlightIdx(idx)}
                        className={clsx(
                          'px-3 py-1.5 text-sm cursor-pointer transition-colors',
                          tagHighlightIdx === idx ? 'bg-primary-50 text-primary-700' : 'text-text hover:bg-gray-50',
                        )}
                      >
                        {tag.name}
                      </li>
                    ))}
                    {showCreateTag && (
                      <li
                        onClick={handleCreateTag}
                        onMouseEnter={() => setTagHighlightIdx(tagSearchResults.length)}
                        className={clsx(
                          'px-3 py-1.5 text-sm cursor-pointer transition-colors flex items-center gap-1.5 border-t border-border',
                          tagHighlightIdx === tagSearchResults.length ? 'bg-primary-50 text-primary-700' : 'text-primary-600 hover:bg-gray-50',
                        )}
                      >
                        <Plus className="h-3.5 w-3.5" />
                        Nieuwe tag: &quot;{tagInput.trim()}&quot;
                      </li>
                    )}
                  </ul>
                )}
              </div>
            </div>
          )}

          {/* Suggested edges + add new edges */}
          <div className="max-w-2xl">
            <h4 className="text-xs font-medium text-text mb-2">
              Verbindingen
              {(sortedSuggestedEdges.length + manualEdges.length > 0) && (
                <span className="text-text-secondary font-normal ml-1">
                  ({sortedSuggestedEdges.length + manualEdges.length})
                </span>
              )}
            </h4>

            {/* Suggested edges list */}
            {sortedSuggestedEdges.length > 0 && (
              <div className="space-y-1.5 mb-2">
                {sortedSuggestedEdges.map((edge) => (
                  <div
                    key={edge.id}
                    className={clsx(
                      'flex items-start gap-2 p-2 rounded-lg bg-gray-50',
                      edge.status === 'rejected' && 'opacity-50',
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        {edge.status === 'pending' ? (
                          <select
                            value={edge.edge_type_id}
                            onChange={(e) => {
                              updateSuggestedEdge.mutate({
                                id: edge.id,
                                data: { edge_type_id: e.target.value },
                              });
                            }}
                            className="text-xs rounded-md border border-border bg-white px-1.5 py-0.5 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                          >
                            {Object.keys(EDGE_TYPE_VOCABULARY).map((key) => (
                              <option key={key} value={key}>
                                {edgeLabel(key)}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <Badge variant="slate">
                            {edgeLabel(edge.edge_type_id)}
                          </Badge>
                        )}
                      </div>
                      {edge.target_node && (
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <Badge
                            variant={NODE_TYPE_COLORS[edge.target_node.node_type]}
                            dot
                          >
                            {nodeLabel(edge.target_node.node_type)}
                          </Badge>
                          <button
                            onClick={() => setModalNodeId(edge.target_node_id)}
                            className="text-sm text-text hover:text-primary-700 truncate transition-colors"
                          >
                            {edge.target_node.title}
                          </button>
                        </div>
                      )}
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-xs text-text-secondary">
                          {Math.round(edge.confidence * 100)}% match
                        </span>
                        {edge.reason && (
                          <span className="text-xs text-text-secondary truncate">
                            — {edge.reason}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Actions on the right */}
                    <div className="flex items-center gap-0.5 shrink-0 mt-1">
                      {edge.status === 'pending' && (
                        <>
                          <button
                            onClick={() => approveEdge.mutate(edge.id)}
                            className="p-1.5 rounded-lg text-green-600 hover:bg-green-100 transition-colors"
                            title="Goedkeuren"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => rejectEdge.mutate(edge.id)}
                            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                            title="Afwijzen"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </>
                      )}
                      {edge.status !== 'pending' && (
                        <button
                          onClick={() => resetEdge.mutate(edge.id)}
                          className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                          title="Ongedaan maken"
                        >
                          <Undo2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Manually added edges */}
            {manualEdges.length > 0 && (
              <div className="space-y-1.5 mb-2">
                {manualEdges.map((edge) => {
                  const isOutgoing = edge.from_node_id === corpusNodeId;
                  const otherNode = isOutgoing ? edge.to_node : edge.from_node;
                  const otherNodeId = isOutgoing ? edge.to_node_id : edge.from_node_id;
                  return (
                    <div
                      key={edge.id}
                      className="flex items-start gap-2 p-2 rounded-lg bg-gray-50"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <Badge variant="slate">
                            {edgeLabel(edge.edge_type_id)}
                          </Badge>
                        </div>
                        {otherNode && (
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <Badge
                              variant={NODE_TYPE_COLORS[otherNode.node_type]}
                              dot
                            >
                              {nodeLabel(otherNode.node_type)}
                            </Badge>
                            <button
                              onClick={() => setModalNodeId(otherNodeId)}
                              className="text-sm text-text hover:text-primary-700 truncate transition-colors"
                            >
                              {otherNode.title}
                            </button>
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() => deleteEdge.mutate(edge.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0 mt-1"
                        title="Verwijderen"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Add edge toggle */}
            {!showAddEdge && (
              corpusNodeId ? (
                <button
                  onClick={() => setShowAddEdge(true)}
                  className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1 transition-colors"
                >
                  <Plus className="h-3 w-3" />
                  Verbinding toevoegen
                </button>
              ) : (
                <p className="text-xs text-text-secondary">
                  Geen corpus-node gekoppeld — verbindingen kunnen niet worden toegevoegd.
                </p>
              )
            )}

            {/* Add new edge form */}
            {showAddEdge && corpusNodeId && (
              <div className="p-3 rounded-lg border border-border bg-gray-50/50 space-y-2">
                <div className="flex items-center gap-2 text-xs font-medium text-text">
                  <Link className="h-3.5 w-3.5" />
                  Nieuwe verbinding
                </div>
                <div className="space-y-2">
                  <CreatableSelect
                    value={newEdgeTargetId}
                    onChange={setNewEdgeTargetId}
                    options={targetOptions}
                    placeholder="Selecteer node..."
                    onCreate={handleCreateNode}
                    createLabel="Nieuw aanmaken"
                  />
                  <CreatableSelect
                    value={newEdgeTypeId}
                    onChange={setNewEdgeTypeId}
                    options={edgeTypeOptions}
                    placeholder="Type verbinding..."
                  />
                </div>
                {createEdge.isError && (
                  <p className="text-xs text-red-600">
                    {(createEdge.error as { body?: { detail?: string } })?.body?.detail || 'Fout bij aanmaken verbinding'}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={handleAddEdge}
                    disabled={!newEdgeTargetId || !newEdgeTypeId || createEdge.isPending}
                    loading={createEdge.isPending}
                  >
                    Toevoegen
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setShowAddEdge(false);
                      setNewEdgeTargetId('');
                      setNewEdgeTypeId('');
                      createEdge.reset();
                    }}
                  >
                    Annuleren
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Follow-up tasks (right below verbindingen) */}
          {item.status === 'imported' && (
            <div className="max-w-2xl">
              <h4 className="text-xs font-medium text-text mb-2">Vervolgacties</h4>
              {followUpTasks.length > 0 && (
                <div className="space-y-2 mb-2">
                  {followUpTasks.map((task, index) => (
                    <div key={index} className="flex items-start gap-2 p-2 rounded-lg bg-gray-50 border border-border">
                      <div className="flex-1 space-y-2">
                        <input
                          type="text"
                          value={task.title}
                          onChange={(e) => updateTaskRow(index, 'title', e.target.value)}
                          placeholder="Omschrijving taak..."
                          className="w-full rounded-lg border border-border px-3 py-1.5 text-sm"
                        />
                        <div className="flex gap-2">
                          <div className="flex-1">
                            <CreatableSelect
                              value={task.assignee_id}
                              onChange={(v) => updateTaskRow(index, 'assignee_id', v)}
                              options={sortedPeopleOptions}
                              placeholder="Toewijzen aan..."
                            />
                          </div>
                          <input
                            type="date"
                            value={task.deadline}
                            onChange={(e) => updateTaskRow(index, 'deadline', e.target.value)}
                            className="rounded-lg border border-border px-3 py-1.5 text-sm"
                          />
                        </div>
                      </div>
                      <button
                        onClick={() => removeTaskRow(index)}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors mt-1"
                        title="Verwijderen"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <button
                onClick={addTaskRow}
                className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1 transition-colors"
              >
                <Plus className="h-3 w-3" />
                Taak toevoegen
              </button>
            </div>
          )}

          {/* Eigenaar — last decision before submit */}
          {item.status === 'imported' && (
            <div className="max-w-xs">
              <CreatableSelect
                label="Eigenaar"
                value={eigenaarId}
                onChange={setEigenaarId}
                options={sortedPeopleOptions}
                placeholder="Selecteer eigenaar..."
              />
            </div>
          )}

          {/* Bottom actions */}
          {item.status === 'imported' && (
            <div className="flex items-center gap-3 pt-2 border-t border-border">
              <Button
                size="sm"
                onClick={handleCompleteSubmit}
                disabled={!eigenaarId || completeReview.isPending}
                loading={completeReview.isPending}
              >
                Beoordeling afronden
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => rejectItem.mutate(item.id)}
              >
                Niet relevant
              </Button>
            </div>
          )}

          {/* Reopen action for rejected/out_of_scope items */}
          {(item.status === 'out_of_scope' || item.status === 'rejected') && (
            <div className="pt-2 border-t border-border">
              <Button
                size="sm"
                variant="ghost"
                icon={<Undo2 className="h-3.5 w-3.5" />}
                onClick={() => reopenItem.mutate(item.id)}
                disabled={reopenItem.isPending}
                loading={reopenItem.isPending}
              >
                Heropenen voor beoordeling
              </Button>
            </div>
          )}
        </div>
      )}
    </Card>
    <NodeDetailModal
      nodeId={modalNodeId}
      open={modalNodeId !== null}
      onClose={() => setModalNodeId(null)}
    />
    </div>
  );
}
