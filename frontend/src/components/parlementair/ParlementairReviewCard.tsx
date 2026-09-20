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
 * `PARLEMENTAIR_TYPE_COLORS` and `SEARCH_RESULT_TYPE_COLORS`-style maps in
 * `@/types` speak the twelve-color `BadgeVariant` palette that `Badge` (the
 * `nldd-tag` wrapper) already understands, so no local remap was needed here —
 * `Badge` takes the existing `BadgeVariant` values directly.
 */

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
 * only (a real navigation target), which this isn't: it opens a modal. So it
 * is `Button` (the `nldd-button` wrapper) at its smallest ghost styling rather
 * than a raw `<button>`.
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
 * create a new tag. The element owns the dropdown state itself: highlight
 * index, click-outside, arrow keys.
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
    {/* The suggestion menu anchors inside this card and must not be clipped. */}
    <Card style={{ overflow: 'visible' }}>
      {/* Clickable header */}
      <nldd-container
        layout="row"
        width="full"
        gap="12"
        horizontal-alignment="right"
        style={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setExpanded(!expanded)}
      >
        <nldd-container gap="4" width="full">
          <nldd-container layout="wrap" gap="6" vertical-alignment="center">
            <Badge variant={typeColor}>
              {typeLabel}
            </Badge>
            <Badge
              variant={PARLEMENTAIR_ITEM_STATUS_COLORS[item.status]}
            >
              {PARLEMENTAIR_ITEM_STATUS_LABELS[item.status]}
            </Badge>
            <nldd-text size="xs" color="secondary">{item.bron === 'tweede_kamer' ? 'Tweede Kamer' : 'Eerste Kamer'}</nldd-text>
            <nldd-text size="xs" color="secondary">{item.zaak_nummer}</nldd-text>
            {item.datum && (
              <nldd-container layout="row" gap="2" vertical-alignment="center">
                <Icon name="calendar" size="xs" />
                <nldd-text size="xs" color="secondary">{formatDateLong(item.datum)}</nldd-text>
              </nldd-container>
            )}
            {item.deadline && (
              <nldd-container layout="row" gap="2" vertical-alignment="center">
                <Icon name="calendar" size="xs" />
                <nldd-text size="xs" color="warning">
                  Deadline: {formatDateLong(item.deadline)}
                </nldd-text>
              </nldd-container>
            )}
            {item.ministerie && (
              <nldd-text size="xs" color="secondary">{item.ministerie}</nldd-text>
            )}
          </nldd-container>
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            <nldd-text size="sm" weight="bold">{item.onderwerp}</nldd-text>
            {item.document_url && (
              <ExternalDocLink href={item.document_url} label="Bekijk op tweedekamer.nl" iconOnly />
            )}
          </nldd-container>
          <nldd-text size="xs" color="secondary">Zaak: {item.titel}</nldd-text>
        </nldd-container>

        <nldd-container layout="row" gap="8" vertical-alignment="center">
          {item.suggested_edges && item.suggested_edges.length > 0 && (
            <nldd-text size="xs" color="secondary">
              {pendingEdges.length} te beoordelen
            </nldd-text>
          )}
          <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size="md" />
        </nldd-container>
      </nldd-container>

      {expanded && (
        <nldd-container gap="20" padding-top="16">
          {/* Quick links bar */}
          <nldd-container layout="row" gap="12" vertical-alignment="center">
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
          </nldd-container>

          {/* Indieners */}
          {item.indieners && item.indieners.length > 0 && (
            <nldd-container gap="6">
              <nldd-container layout="row" gap="4" vertical-alignment="center">
                <Icon name="users" size="sm" />
                <nldd-text size="xs" weight="medium">Indieners</nldd-text>
              </nldd-container>
              <nldd-container layout="wrap" gap="4">
                {item.indieners.map((indiener) => (
                  <Badge key={indiener} variant="purple">{indiener}</Badge>
                ))}
              </nldd-container>
            </nldd-container>
          )}

          {/* Summary */}
          {item.llm_samenvatting && (
            <nldd-container gap="4">
              <nldd-text size="xs" weight="medium">Samenvatting</nldd-text>
              <nldd-text size="sm" color="secondary">
                <MarkdownRenderer content={item.llm_samenvatting} />
              </nldd-text>
            </nldd-container>
          )}

          {/* Document text */}
          {item.document_tekst && (
            <nldd-container gap="4">
              <nldd-text size="xs" weight="medium">Tekst</nldd-text>
              {/* whitespace-pre-wrap has no nldd-text equivalent (the component
                  does not expose white-space control), so this stays a plain
                  element; the scroll box and tinted background are likewise
                  presentational chrome around a text dump rather than a
                  document composition, so nldd-container's background isn't a
                  fit either. */}
              <nldd-text
                size="sm"
                color="secondary"
                className="whitespace-pre-wrap surface-tinted"
                style={{
                  borderRadius: 'var(--primitives-corner-radius-md)',
                  padding: '12px',
                  maxHeight: '192px',
                  overflowY: 'auto',
                }}
              >
                {item.document_tekst}
              </nldd-text>
            </nldd-container>
          )}

          {/* Matched tags */}
          {item.matched_tags && item.matched_tags.length > 0 && (
            <nldd-container gap="6">
              <nldd-text size="xs" weight="medium">Gematchte tags</nldd-text>
              <nldd-container layout="wrap" gap="4">
                {item.matched_tags.map((tag) => (
                  <Badge key={tag} variant="slate">{tag}</Badge>
                ))}
              </nldd-container>
            </nldd-container>
          )}

          {/* Tags on corpus node */}
          {corpusNodeId && (
            <nldd-container gap="6" max-width="320px">
              <nldd-text size="xs" weight="medium">Tags</nldd-text>
              <TagTokenField
                nodeTags={nodeTags}
                allTags={allTags}
                onAdd={(tagId) => addTag.mutate({ nodeId: corpusNodeId, data: { tag_id: tagId } })}
                onAddNew={(tagName) => addTag.mutate({ nodeId: corpusNodeId, data: { tag_name: tagName } })}
                onRemove={(tagId) => removeTag.mutate({ nodeId: corpusNodeId, tagId })}
              />
            </nldd-container>
          )}

          {/* Suggested edges + add new edges */}
          <nldd-container gap="8" max-width="672px">
            <nldd-text size="xs" weight="medium">
              Verbindingen
              {(sortedSuggestedEdges.length + manualEdges.length > 0) &&
                ` (${sortedSuggestedEdges.length + manualEdges.length})`}
            </nldd-text>

            {/* Suggested edges list */}
            {sortedSuggestedEdges.length > 0 && (
              <nldd-list type="list" variant="box-tinted" dividers="always">
                {sortedSuggestedEdges.map((edge) => (
                  <nldd-list-item key={edge.id} style={edge.status === 'rejected' ? { opacity: 0.5 } : undefined}>
                    <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="top">
                      <nldd-container gap="2" width="full">
                        <nldd-container layout="row" gap="6" vertical-alignment="center">
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
                        </nldd-container>
                        {edge.target_node && (
                          <nldd-container layout="row" gap="6" vertical-alignment="center">
                            <Badge variant={NODE_TYPE_COLORS[edge.target_node.node_type]} dot>
                              {nodeLabel(edge.target_node.node_type)}
                            </Badge>
                            <NlddButtonLink
                              text={edge.target_node.title}
                              onClick={() => setModalNodeId(edge.target_node_id)}
                            />
                          </nldd-container>
                        )}
                        <nldd-container layout="row" gap="6" vertical-alignment="center">
                          <nldd-text size="xs" color="secondary">
                            {Math.round(edge.confidence * 100)}% match
                          </nldd-text>
                          {edge.reason && (
                            <nldd-text size="xs" color="secondary">
                              — {edge.reason}
                            </nldd-text>
                          )}
                        </nldd-container>
                      </nldd-container>

                      {/* Actions on the right */}
                      <nldd-container layout="row" gap="2" vertical-alignment="center" padding-top="4">
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
                      </nldd-container>
                    </nldd-container>
                  </nldd-list-item>
                ))}
              </nldd-list>
            )}

            {/* Manually added edges */}
            {manualEdges.length > 0 && (
              <nldd-list type="list" variant="box-tinted" dividers="always">
                {manualEdges.map((edge) => {
                  const isOutgoing = edge.from_node_id === corpusNodeId;
                  const otherNode = isOutgoing ? edge.to_node : edge.from_node;
                  const otherNodeId = isOutgoing ? edge.to_node_id : edge.from_node_id;
                  return (
                    <nldd-list-item key={edge.id}>
                      <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="top">
                        <nldd-container gap="2" width="full">
                          <nldd-container layout="row" gap="6" vertical-alignment="center">
                            <Badge variant="slate">{edgeLabel(edge.edge_type_id)}</Badge>
                          </nldd-container>
                          {otherNode && (
                            <nldd-container layout="row" gap="6" vertical-alignment="center">
                              <Badge variant={NODE_TYPE_COLORS[otherNode.node_type]} dot>
                                {nodeLabel(otherNode.node_type)}
                              </Badge>
                              <NlddButtonLink
                                text={otherNode.title}
                                onClick={() => setModalNodeId(otherNodeId)}
                              />
                            </nldd-container>
                          )}
                        </nldd-container>
                        <NlddIconButton
                          icon="trash"
                          accessibleLabel="Verwijderen"
                          variant="neutral-transparent"
                          size="sm"
                          onClick={() => deleteEdge.mutate(edge.id)}
                        />
                      </nldd-container>
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
                <nldd-text size="xs" color="secondary">
                  Geen corpus-node gekoppeld — verbindingen kunnen niet worden toegevoegd.
                </nldd-text>
              )
            )}

            {/* Add new edge form */}
            {showAddEdge && corpusNodeId && (
              <nldd-list variant="box-tinted">
                <nldd-list-item>
                  <nldd-container gap="8" width="full" padding="4">
                    <nldd-container layout="row" gap="6" vertical-alignment="center">
                      <Icon name="link" size="sm" />
                      <nldd-text size="xs" weight="medium">Nieuwe verbinding</nldd-text>
                    </nldd-container>
                    <nldd-container gap="8">
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
                    </nldd-container>
                    {createEdge.isError && (
                      <nldd-text size="xs" color="critical">
                        {(createEdge.error as { body?: { detail?: string } })?.body?.detail || 'Fout bij aanmaken verbinding'}
                      </nldd-text>
                    )}
                    <nldd-container layout="row" gap="8" vertical-alignment="center">
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
                    </nldd-container>
                  </nldd-container>
                </nldd-list-item>
              </nldd-list>
            )}
          </nldd-container>

          {/* Follow-up tasks (right below verbindingen) */}
          {item.status === 'imported' && (
            <nldd-container gap="8" max-width="672px">
              <nldd-text size="xs" weight="medium">Vervolgacties</nldd-text>
              {followUpTasks.length > 0 && (
                <nldd-list variant="box-tinted">
                  {followUpTasks.map((task, index) => (
                    <nldd-list-item key={index}>
                      <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="top" padding="4">
                        <nldd-container gap="8" width="full">
                          <FollowUpTitleField
                            value={task.title}
                            onChange={(v) => updateTaskRow(index, 'title', v)}
                          />
                          <nldd-container layout="row" gap="8">
                            <nldd-container width="full">
                              <CreatableSelect
                                value={task.assignee_id}
                                onChange={(v) => updateTaskRow(index, 'assignee_id', v)}
                                options={sortedPeopleOptions}
                                placeholder="Toewijzen aan..."
                              />
                            </nldd-container>
                            <FollowUpDeadlineField
                              value={task.deadline}
                              onChange={(v) => updateTaskRow(index, 'deadline', v)}
                            />
                          </nldd-container>
                        </nldd-container>
                        <NlddIconButton
                          icon="trash"
                          accessibleLabel="Verwijderen"
                          variant="neutral-transparent"
                          size="sm"
                          onClick={() => removeTaskRow(index)}
                        />
                      </nldd-container>
                    </nldd-list-item>
                  ))}
                </nldd-list>
              )}
              <Button variant="ghost" size="sm" icon="plus" onClick={addTaskRow}>
                Taak toevoegen
              </Button>
            </nldd-container>
          )}

          {/* Eigenaar — last decision before submit */}
          {item.status === 'imported' && (
            <nldd-container max-width="320px">
              <CreatableSelect
                label="Eigenaar"
                value={eigenaarId}
                onChange={setEigenaarId}
                options={sortedPeopleOptions}
                placeholder="Selecteer eigenaar..."
              />
            </nldd-container>
          )}

          {/* Bottom actions */}
          {item.status === 'imported' && (
            <nldd-container layout="row" gap="12" vertical-alignment="center" padding-top="8">
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
            </nldd-container>
          )}

          {/* Reopen action for rejected/out_of_scope items */}
          {(item.status === 'out_of_scope' || item.status === 'rejected') && (
            <nldd-container padding-top="8">
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
            </nldd-container>
          )}
        </nldd-container>
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
