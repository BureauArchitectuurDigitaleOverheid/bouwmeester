import { useState, useEffect, useRef, useCallback } from 'react';
import { ChevronDown, ChevronUp, Check, X, ExternalLink, Users, Calendar, Plus, Trash2, Link } from 'lucide-react';
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
  useUpdateSuggestedEdge,
  useRejectParlementairItem,
  useCompleteParlementairReview,
} from '@/hooks/useParlementair';
import { useCreateEdge } from '@/hooks/useEdges';
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
} from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { EDGE_TYPE_VOCABULARY } from '@/vocabulary';
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
  const updateSuggestedEdge = useUpdateSuggestedEdge();
  const rejectItem = useRejectParlementairItem();
  const completeReview = useCompleteParlementairReview();
  const createEdge = useCreateEdge();
  const createNode = useCreateNode();
  const { data: people } = usePeople();
  const { data: allNodes } = useNodes();
  const { data: allTags } = useTags();
  const { data: nodeTags } = useNodeTags(item.corpus_node_id ?? '');
  const addTag = useAddTagToNode();
  const removeTag = useRemoveTagFromNode();

  const corpusNodeId = item.corpus_node_id;

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
        setTagHighlightIdx((i) => (i + 1) % tagTotalItems);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setTagHighlightIdx((i) => (i - 1 + tagTotalItems) % tagTotalItems);
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
    await createEdge.mutateAsync({
      from_node_id: corpusNodeId,
      to_node_id: newEdgeTargetId,
      edge_type_id: newEdgeTypeId,
    });
    setNewEdgeTargetId('');
    setNewEdgeTypeId('');
    setShowAddEdge(false);
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

  const pendingEdges = item.suggested_edges?.filter((e) => e.status === 'pending') ?? [];

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    try {
      return new Date(dateStr).toLocaleDateString('nl-NL', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

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
            <Badge variant={typeColor as 'blue'}>
              {typeLabel}
            </Badge>
            <Badge
              variant={PARLEMENTAIR_ITEM_STATUS_COLORS[item.status] as 'blue'}
            >
              {PARLEMENTAIR_ITEM_STATUS_LABELS[item.status]}
            </Badge>
            <span className="text-xs text-text-secondary">{item.bron === 'tweede_kamer' ? 'Tweede Kamer' : 'Eerste Kamer'}</span>
            <span className="text-xs text-text-secondary">{item.zaak_nummer}</span>
            {item.datum && (
              <span className="text-xs text-text-secondary flex items-center gap-0.5">
                <Calendar className="h-3 w-3" />
                {formatDate(item.datum)}
              </span>
            )}
            {item.deadline && (
              <span className="text-xs text-orange-600 flex items-center gap-0.5">
                <Calendar className="h-3 w-3" />
                Deadline: {formatDate(item.deadline)}
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
        <div className="mt-4 pt-4 border-t border-border space-y-4">
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
              <div className="relative max-w-sm" ref={tagContainerRef}>
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
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-medium text-text">
                Verbindingen
                {item.suggested_edges && item.suggested_edges.length > 0 && (
                  <span className="text-text-secondary font-normal ml-1">
                    ({item.suggested_edges.length} voorgesteld)
                  </span>
                )}
              </h4>
              {corpusNodeId && (
                <button
                  onClick={() => setShowAddEdge(!showAddEdge)}
                  className="text-xs text-primary-700 hover:text-primary-800 flex items-center gap-1"
                >
                  <Plus className="h-3 w-3" />
                  Verbinding toevoegen
                </button>
              )}
            </div>

            {/* Suggested edges list */}
            {item.suggested_edges && item.suggested_edges.length > 0 && (
              <div className="space-y-2 mb-2">
                {item.suggested_edges.map((edge) => (
                  <div
                    key={edge.id}
                    className="flex items-center gap-3 p-2 rounded-lg bg-gray-50"
                  >
                    <div className="flex-1 min-w-0">
                      {edge.target_node && (
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={NODE_TYPE_COLORS[edge.target_node.node_type] as 'blue'}
                            dot
                          >
                            {nodeLabel(edge.target_node.node_type)}
                          </Badge>
                          <button
                            onClick={() => navigate(`/nodes/${edge.target_node_id}`)}
                            className="text-sm text-text hover:text-primary-700 truncate transition-colors"
                          >
                            {edge.target_node.title}
                          </button>
                        </div>
                      )}
                      <div className="flex items-center gap-2 mt-1">
                        {edge.status === 'pending' ? (
                          <select
                            value={edge.edge_type_id}
                            onChange={(e) => {
                              updateSuggestedEdge.mutate({
                                id: edge.id,
                                data: { edge_type_id: e.target.value },
                              });
                            }}
                            className="text-xs rounded-md border border-border bg-white px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
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
                        <span className="text-xs text-text-secondary">
                          {Math.round(edge.confidence * 100)}%
                        </span>
                        {edge.reason && (
                          <span className="text-xs text-text-secondary">
                            — {edge.reason}
                          </span>
                        )}
                      </div>
                    </div>

                    {edge.status === 'pending' ? (
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => approveEdge.mutate(edge.id)}
                          className="p-1.5 rounded-lg bg-green-50 text-green-600 hover:bg-green-100 transition-colors"
                          title="Goedkeuren"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => rejectEdge.mutate(edge.id)}
                          className="p-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors"
                          title="Afwijzen"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <Badge variant={edge.status === 'approved' ? 'green' : 'gray'}>
                        {edge.status === 'approved' ? 'Goedgekeurd' : 'Afgewezen'}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Add new edge form */}
            {showAddEdge && corpusNodeId && (
              <div className="p-3 rounded-lg border border-border bg-gray-50/50 space-y-3">
                <div className="flex items-center gap-2 text-xs font-medium text-text">
                  <Link className="h-3.5 w-3.5" />
                  Nieuwe verbinding
                </div>
                <div className="grid grid-cols-2 gap-2">
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
                    }}
                  >
                    Annuleren
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Eigenaar + follow-up tasks (inline, always visible for imported items) */}
          {item.status === 'imported' && (
            <div className="p-4 rounded-xl border border-primary-200 bg-primary-50/50 space-y-4">
              <h4 className="text-sm font-semibold text-text">Beoordeling</h4>

              {/* Eigenaar selector */}
              <div className="max-w-sm">
                <CreatableSelect
                  label="Eigenaar toewijzen"
                  value={eigenaarId}
                  onChange={setEigenaarId}
                  options={(people ?? []).map((p) => ({
                    value: p.id,
                    label: p.naam,
                    description: p.functie || undefined,
                  }))}
                  placeholder="Selecteer eigenaar..."
                />
              </div>

              {/* Follow-up tasks */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h5 className="text-xs font-medium text-text">Vervolgacties</h5>
                  <button
                    onClick={addTaskRow}
                    className="text-xs text-primary-700 hover:text-primary-800 flex items-center gap-1"
                  >
                    <Plus className="h-3 w-3" />
                    Taak toevoegen
                  </button>
                </div>
                {followUpTasks.length > 0 && (
                  <div className="space-y-2">
                    {followUpTasks.map((task, index) => (
                      <div key={index} className="flex items-start gap-2 p-2 rounded-lg bg-white border border-border">
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
                                options={(people ?? []).map((p) => ({
                                  value: p.id,
                                  label: p.naam,
                                  description: p.functie || undefined,
                                }))}
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
                          className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors mt-1"
                          title="Verwijderen"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Submit button */}
              <Button
                size="sm"
                onClick={handleCompleteSubmit}
                disabled={!eigenaarId || completeReview.isPending}
                loading={completeReview.isPending}
              >
                Beoordeling afronden
              </Button>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2">
            {item.status === 'imported' && (
              <Button
                size="sm"
                variant="ghost"
                className="text-red-500 hover:bg-red-50"
                onClick={() => rejectItem.mutate(item.id)}
              >
                Niet relevant
              </Button>
            )}
            {item.corpus_node_id && (
              <Button
                size="sm"
                variant="secondary"
                icon={<ExternalLink className="h-3.5 w-3.5" />}
                onClick={() => navigate(`/nodes/${item.corpus_node_id}`)}
              >
                Bekijk node
              </Button>
            )}
            {item.document_url && (
              <a
                href={item.document_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<ExternalLink className="h-3.5 w-3.5" />}
                >
                  Bekijk op tweedekamer.nl
                </Button>
              </a>
            )}
          </div>
        </div>
      )}
    </Card>
    </div>
  );
}
