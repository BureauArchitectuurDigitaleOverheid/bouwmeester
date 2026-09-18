import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Select } from '@/components/common/Select';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { eventValue, useNlddEvent, useNlddValue } from '@/components/nldd/events';
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
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { buildPersonOptions } from '@/utils/personOptions';
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
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { NodeDetailModal } from '@/components/nodes/NodeDetailModal';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { EDGE_TYPE_VOCABULARY } from '@/vocabulary';
import { formatDateLong } from '@/utils/dates';
import type { CompleteReviewData, NodeTagResponse, Tag } from '@/types';

interface FollowUpTaskRow {
  title: string;
  assignee_id: string;
  deadline: string;
}

/**
 * An `nldd-link` that stops its click from bubbling into a clickable ancestor
 * row (the card header toggles `expanded` on click). Click has to go through
 * `useNlddEvent` rather than a React `onClick` prop for consistency with the
 * rest of this codebase's nldd bindings.
 */
function ExternalDocLink({
  href,
  label,
  iconOnly,
}: {
  href: string;
  label: string;
  iconOnly?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', useCallback((e: Event) => e.stopPropagation(), []));

  return (
    <nldd-link
      ref={ref}
      href={href}
      target="_blank"
      size={iconOnly ? undefined : 'xs'}
      {...(iconOnly ? { 'accessible-label': label } : { text: label, 'end-icon': 'external-link' })}
    >
      {iconOnly && <Icon name="external-link" size="sm" />}
    </nldd-link>
  );
}

/**
 * A node title that opens `NodeDetailModal` on click. `nldd-link` is `href`-
 * only (a real navigation target), which this isn't — it opens a modal — so
 * this is `Button` (the converted `nldd-button` wrapper) at its smallest
 * ghost styling instead of a raw `<button>`.
 */
function NlddButtonLink({ text, onClick }: { text: string; onClick: () => void }) {
  return (
    <Button variant="ghost" size="sm" onClick={onClick} className="truncate">
      {text}
    </Button>
  );
}

/** A controlled `nldd-text-field` for a follow-up task's title. */
function FollowUpTitleField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddValue(ref, value);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return <nldd-text-field ref={ref} placeholder="Omschrijving taak..." accessible-label="Omschrijving taak" />;
}

/** A controlled `nldd-date-field` for a follow-up task's deadline. */
function FollowUpDeadlineField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddValue(ref, value);
  useNlddEvent(ref, 'change', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return <nldd-date-field ref={ref} accessible-label="Deadline" />;
}

interface TagTokenFieldProps {
  nodeTags: NodeTagResponse[] | undefined;
  allTags: Tag[] | undefined;
  onAdd: (tagId: string) => void;
  onAddNew: (tagName: string) => void;
  onRemove: (tagId: string) => void;
}

/**
 * `nldd-token-field` for the corpus node's tags: chips are the existing tags
 * (dismissible), the slotted menu is every known tag (the field hides options
 * already present as tokens itself, see `_hideSelectedMenuItems` in
 * token-field.js), and `allow-custom` lets a typed name that matches nothing
 * create a new tag. This replaces ~70 lines of hand-rolled dropdown state
 * (highlight index, click-outside, arrow keys) that the element owns itself.
 *
 * `.values` is a live property, not a reflected attribute — like
 * `CreatableSelect`'s `.text`, it is written imperatively only when it has
 * actually diverged from the tags this node has, to avoid fighting the
 * element's own state while the user is mid-selection.
 */
function TagTokenField({ nodeTags, allTags, onAdd, onAddNew, onRemove }: TagTokenFieldProps) {
  const ref = useRef<HTMLElement & { values?: string[] }>(null);
  const currentIds = useMemo(() => (nodeTags ?? []).map((nt) => nt.tag.id), [nodeTags]);
  const tagById = useMemo(() => new Map((allTags ?? []).map((t) => [t.id, t])), [allTags]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const current = el.values ?? [];
    if (current.length !== currentIds.length || !currentIds.every((id) => current.includes(id))) {
      el.values = currentIds;
    }
  }, [currentIds]);

  const handleChange = useCallback(
    (event: Event) => {
      const nextValues = (event as CustomEvent<{ values?: string[] }>).detail?.values ?? [];
      const added = nextValues.find((v) => !currentIds.includes(v));
      const removedId = currentIds.find((id) => !nextValues.includes(id));
      if (removedId) {
        onRemove(removedId);
      } else if (added) {
        // A known tag id commits as itself; free text (no matching menu item,
        // hence no id) commits as its own typed name.
        if (tagById.has(added)) onAdd(added);
        else onAddNew(added);
      }
    },
    [currentIds, tagById, onAdd, onAddNew, onRemove],
  );
  useNlddEvent(ref, 'change', handleChange);

  return (
    <nldd-token-field
      ref={ref}
      placeholder="Tag zoeken of toevoegen..."
      allow-custom
      accessible-label="Tags"
    >
      <nldd-menu>
        {(allTags ?? []).map((tag) => (
          <nldd-menu-item key={tag.id} value={tag.id} text={tag.name} />
        ))}
      </nldd-menu>
    </nldd-token-field>
  );
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
  const [modalNodeId, setModalNodeId] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
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
  const { currentPerson } = useCurrentPerson();
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

  // People options sorted: self first, then relevant eigenaren, then the rest
  const sortedPeople = [...(people ?? [])].sort((a, b) => {
    const aRel = relevantPersonIds.has(a.id);
    const bRel = relevantPersonIds.has(b.id);
    if (aRel !== bRel) return aRel ? -1 : 1;
    return a.naam.localeCompare(b.naam);
  });
  const sortedPeopleOptions: SelectOption[] = buildPersonOptions(
    sortedPeople, currentPerson, (p) => ({
      value: p.id,
      label: p.naam,
      description: functieLabel(p.functie),
    }),
  );

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
    <Card className="overflow-visible">
      {/* Clickable header */}
      <div
        className="flex items-start justify-between gap-3 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-1">
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
                <Icon name="calendar" size="xs" />
                {formatDateLong(item.datum)}
              </span>
            )}
            {item.deadline && (
              <nldd-text size="xs" color="warning" className="flex items-center gap-0.5">
                <Icon name="calendar" size="xs" />
                Deadline: {formatDateLong(item.deadline)}
              </nldd-text>
            )}
            {item.ministerie && (
              <span className="text-xs text-text-secondary">{item.ministerie}</span>
            )}
          </div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-text">{item.onderwerp}</h3>
            {item.document_url && (
              <ExternalDocLink href={item.document_url} label="Bekijk op tweedekamer.nl" iconOnly />
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
            <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size="md" />
          </div>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border space-y-5">
          {/* Quick links bar */}
          <div className="flex items-center gap-3">
            {item.corpus_node_id && (
              <Button
                variant="ghost"
                size="sm"
                icon="external-link"
                onClick={() => navigate(`/nodes/${item.corpus_node_id}`)}
              >
                Bekijk node
              </Button>
            )}
            {item.document_url && (
              <ExternalDocLink href={item.document_url} label="Bekijk op tweedekamer.nl" />
            )}
          </div>

          {/* Indieners */}
          {item.indieners && item.indieners.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1.5 flex items-center gap-1">
                <Icon name="users" size="sm" />
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
              <div className="text-sm text-text-secondary">
                <MarkdownRenderer content={item.llm_samenvatting} />
              </div>
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
            <div className="max-w-xs">
              <h4 className="text-xs font-medium text-text mb-1.5">Tags</h4>
              <TagTokenField
                nodeTags={nodeTags}
                allTags={allTags}
                onAdd={(tagId) => addTag.mutate({ nodeId: corpusNodeId, data: { tag_id: tagId } })}
                onAddNew={(tagName) => addTag.mutate({ nodeId: corpusNodeId, data: { tag_name: tagName } })}
                onRemove={(tagId) => removeTag.mutate({ nodeId: corpusNodeId, tagId })}
              />
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
              <nldd-list type="list" variant="box-tinted" dividers="always" className="mb-2">
                {sortedSuggestedEdges.map((edge) => (
                  <nldd-list-item key={edge.id} style={edge.status === 'rejected' ? { opacity: 0.5 } : undefined}>
                    <div className="flex items-start gap-2 w-full py-1">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          {edge.status === 'pending' ? (
                            <Select
                              value={edge.edge_type_id}
                              onChange={(e) =>
                                updateSuggestedEdge.mutate({
                                  id: edge.id,
                                  data: { edge_type_id: e.target.value },
                                })
                              }
                              options={Object.keys(EDGE_TYPE_VOCABULARY).map((key) => ({
                                value: key,
                                label: edgeLabel(key),
                              }))}
                            />
                          ) : (
                            <Badge variant="slate">{edgeLabel(edge.edge_type_id)}</Badge>
                          )}
                        </div>
                        {edge.target_node && (
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <Badge variant={NODE_TYPE_COLORS[edge.target_node.node_type]} dot>
                              {nodeLabel(edge.target_node.node_type)}
                            </Badge>
                            <NlddButtonLink
                              text={edge.target_node.title}
                              onClick={() => setModalNodeId(edge.target_node_id)}
                            />
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
                            <NlddIconButton
                              icon="check-mark"
                              accessibleLabel="Goedkeuren"
                              variant="neutral-transparent"
                              size="sm"
                              onClick={() => approveEdge.mutate(edge.id)}
                            />
                            <NlddIconButton
                              icon="trash"
                              accessibleLabel="Afwijzen"
                              variant="neutral-transparent"
                              size="sm"
                              onClick={() => rejectEdge.mutate(edge.id)}
                            />
                          </>
                        )}
                        {edge.status !== 'pending' && (
                          <NlddIconButton
                            icon="undo"
                            accessibleLabel="Ongedaan maken"
                            variant="neutral-transparent"
                            size="sm"
                            onClick={() => resetEdge.mutate(edge.id)}
                          />
                        )}
                      </div>
                    </div>
                  </nldd-list-item>
                ))}
              </nldd-list>
            )}

            {/* Manually added edges */}
            {manualEdges.length > 0 && (
              <nldd-list type="list" variant="box-tinted" dividers="always" className="mb-2">
                {manualEdges.map((edge) => {
                  const isOutgoing = edge.from_node_id === corpusNodeId;
                  const otherNode = isOutgoing ? edge.to_node : edge.from_node;
                  const otherNodeId = isOutgoing ? edge.to_node_id : edge.from_node_id;
                  return (
                    <nldd-list-item key={edge.id}>
                      <div className="flex items-start gap-2 w-full py-1">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <Badge variant="slate">{edgeLabel(edge.edge_type_id)}</Badge>
                          </div>
                          {otherNode && (
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <Badge variant={NODE_TYPE_COLORS[otherNode.node_type]} dot>
                                {nodeLabel(otherNode.node_type)}
                              </Badge>
                              <NlddButtonLink
                                text={otherNode.title}
                                onClick={() => setModalNodeId(otherNodeId)}
                              />
                            </div>
                          )}
                        </div>
                        <NlddIconButton
                          icon="trash"
                          accessibleLabel="Verwijderen"
                          variant="neutral-transparent"
                          size="sm"
                          onClick={() => deleteEdge.mutate(edge.id)}
                        />
                      </div>
                    </nldd-list-item>
                  );
                })}
              </nldd-list>
            )}

            {/* Add edge toggle */}
            {!showAddEdge && (
              corpusNodeId ? (
                <Button variant="ghost" size="sm" icon="plus" onClick={() => setShowAddEdge(true)}>
                  Verbinding toevoegen
                </Button>
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
                  <Icon name="link" size="sm" />
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
                  <nldd-text size="xs" color="critical">
                    {(createEdge.error as { body?: { detail?: string } })?.body?.detail || 'Fout bij aanmaken verbinding'}
                  </nldd-text>
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
                        <FollowUpTitleField
                          value={task.title}
                          onChange={(v) => updateTaskRow(index, 'title', v)}
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
                          <FollowUpDeadlineField
                            value={task.deadline}
                            onChange={(v) => updateTaskRow(index, 'deadline', v)}
                          />
                        </div>
                      </div>
                      <NlddIconButton
                        icon="trash"
                        accessibleLabel="Verwijderen"
                        variant="neutral-transparent"
                        size="sm"
                        onClick={() => removeTaskRow(index)}
                      />
                    </div>
                  ))}
                </div>
              )}
              <Button variant="ghost" size="sm" icon="plus" onClick={addTaskRow}>
                Taak toevoegen
              </Button>
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
                icon="undo"
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
