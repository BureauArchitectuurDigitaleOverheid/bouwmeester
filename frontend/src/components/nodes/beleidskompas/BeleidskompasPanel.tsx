import { useRef, useState, useMemo } from 'react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Icon } from '@/components/nldd/Icon';
import { useNlddEvent } from '@/components/nldd/events';
import { useNodeGraph } from '@/hooks/useNodes';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useCompletenessAnalysis, type StepStatus } from './useCompletenessAnalysis';
import { KCBR_MAIN_URL, KCBR_STAKEHOLDERS_URL } from './config';
import { GapAnalysisPanel } from './GapAnalysisPanel';
import { KompasStepSuggestions } from './KompasStepSuggestions';
import { LinkExistingNodeModal } from './LinkExistingNodeModal';
import { NodeCreateForm } from '../NodeCreateForm';
import { NODE_TYPE_LABELS, NODE_TYPE_LABELS_PLURAL, NODE_TYPE_COLORS, type NodeType } from '@/types';
import { EDGE_TYPE_ONDERDEEL_VAN } from './constants';

/** An `nldd-list-item[button]` row with its click bridged to React. */
function ClickableListItem({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return (
    <nldd-list-item ref={ref} button>
      {children}
    </nldd-list-item>
  );
}

/**
 * A segment that discloses a row's children group: a chevron that flips, and a
 * click bridged to React. Sits beside a sibling segment (the KCBR link) so the
 * two actions stay independent rather than nesting a control inside a control.
 */
function DisclosureSegment({
  expanded,
  onToggle,
  children,
}: {
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onToggle);
  return (
    <nldd-list-item-segment ref={ref} button width="full" expanded={expanded ? true : undefined}>
      {children}
      <nldd-icon-cell icon="chevron-down" size="16" className={expanded ? 'rotate-180' : undefined} />
    </nldd-list-item-segment>
  );
}

/** An `nldd-link` with its click bridged to React, for an in-page action rather than navigation. */
function ActionLink({ text, onClick }: { text: string; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return <nldd-link ref={ref} text={text} size="xs" />;
}

interface StepActionButtonsProps {
  nodeType: NodeType;
  onCreateNew: (nodeType: NodeType) => void;
  onLinkExisting: (nodeType: NodeType) => void;
}

function StepActionButtons({ nodeType, onCreateNew, onLinkExisting }: StepActionButtonsProps) {
  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="sm"
        icon="plus"
        onClick={() => onCreateNew(nodeType)}
      >
        Nieuw
      </Button>
      <Button
        variant="ghost"
        size="sm"
        icon="link"
        onClick={() => onLinkExisting(nodeType)}
      >
        Koppelen
      </Button>
    </div>
  );
}

interface BeleidskompasStepRowProps {
  status: StepStatus;
  dossierId: string;
  onCreateNew: (nodeType: NodeType) => void;
  onLinkExisting: (nodeType: NodeType) => void;
}

function StepNumberBadge({ number, complete }: { number: number; complete: boolean }) {
  return <nldd-badge number={number} color={complete ? 'success' : 'neutral'} size="md" />;
}

function stepCountLabel(status: StepStatus): string {
  if (status.step.nodeTypes.length === 1) {
    const nt = status.step.nodeTypes[0];
    if (status.count === 1) return `1 ${NODE_TYPE_LABELS[nt].toLowerCase()}`;
    return `${status.count} ${NODE_TYPE_LABELS_PLURAL[nt] ?? NODE_TYPE_LABELS[nt].toLowerCase()}`;
  }
  // Multi-type step: use pre-computed counts per type
  const parts: string[] = [];
  for (const nt of status.step.nodeTypes) {
    const count = status.countsByType.get(nt) ?? 0;
    if (count === 0) continue;
    const label = count === 1
      ? NODE_TYPE_LABELS[nt].toLowerCase()
      : (NODE_TYPE_LABELS_PLURAL[nt] ?? NODE_TYPE_LABELS[nt].toLowerCase());
    parts.push(`${count} ${label}`);
  }
  return parts.join(', ');
}

/** Renders nodes and action buttons grouped by node type for a step. */
function StepTypeGroups({
  status,
  onCreateNew,
  onLinkExisting,
}: {
  status: StepStatus;
  onCreateNew: (nodeType: NodeType) => void;
  onLinkExisting: (nodeType: NodeType) => void;
}) {
  const { openNodeDetail } = useNodeDetail();
  const isMultiType = status.step.nodeTypes.length > 1;

  if (!isMultiType) {
    // Single type: show nodes flat, then action buttons
    return (
      <>
        {status.nodes.map((node) => (
          <ClickableListItem key={node.id} onClick={() => openNodeDetail(node.id)}>
            <nldd-text-cell width="fit-content">
              <Badge variant={NODE_TYPE_COLORS[node.node_type as NodeType]} dot>
                {NODE_TYPE_LABELS[node.node_type as NodeType]}
              </Badge>
            </nldd-text-cell>
            <nldd-text-cell text={node.title} />
          </ClickableListItem>
        ))}
        <StepActionButtons
          nodeType={status.step.nodeTypes[0]}
          onCreateNew={onCreateNew}
          onLinkExisting={onLinkExisting}
        />
      </>
    );
  }

  // Multi-type: group nodes and actions per type
  return (
    <div className="space-y-2">
      {status.step.nodeTypes.map((nt) => {
        const typeNodes = status.nodes.filter(
          (n) => n.node_type === nt,
        );
        return (
          <div key={nt}>
            <div className="flex items-center gap-2 mb-1">
              <nldd-text size="xs" color="secondary" weight="medium" className="min-w-[100px] inline-block">
                {NODE_TYPE_LABELS[nt]}:
              </nldd-text>
            </div>
            <div className="ml-2">
              {typeNodes.map((node) => (
                <ClickableListItem key={node.id} onClick={() => openNodeDetail(node.id)}>
                  <nldd-text-cell width="fit-content">
                    <Badge variant={NODE_TYPE_COLORS[node.node_type as NodeType]} dot>
                      {NODE_TYPE_LABELS[node.node_type as NodeType]}
                    </Badge>
                  </nldd-text-cell>
                  <nldd-text-cell text={node.title} />
                </ClickableListItem>
              ))}
            </div>
            <div className="ml-2">
              <StepActionButtons
                nodeType={nt}
                onCreateNew={onCreateNew}
                onLinkExisting={onLinkExisting}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BeleidskompasStepRow({ status, dossierId, onCreateNew, onLinkExisting }: BeleidskompasStepRowProps) {
  const [expanded, setExpanded] = useState(false);

  if (status.isComplete) {
    return (
      <div className="border-b border-border last:border-b-0">
        <nldd-list-item>
          <DisclosureSegment expanded={expanded} onToggle={() => setExpanded((e) => !e)}>
            <nldd-icon-cell icon="check-mark-circle" color="success" />
            <StepNumberBadge number={status.step.number} complete />
            <nldd-title-cell text={status.step.question} />
            <nldd-text-cell width="fit-content" color="secondary" hide-below="sm" text={stepCountLabel(status)} />
          </DisclosureSegment>
          <nldd-list-item-segment href={status.step.kcbrUrl} target="_blank" width="fit-content" accessible-label="Bekijk op KCBR">
            <nldd-icon-cell icon="external-link" size="16" />
          </nldd-list-item-segment>
        </nldd-list-item>
        {expanded && (
          <div className="px-3 sm:px-4 pb-3 space-y-1.5 ml-9 sm:ml-10">
            <StepTypeGroups
              status={status}
              onCreateNew={onCreateNew}
              onLinkExisting={onLinkExisting}
            />
          </div>
        )}
      </div>
    );
  }

  // Incomplete step (may still have some nodes linked)
  return (
    <div className="border-b border-border last:border-b-0">
      <div className="px-3 py-2.5 sm:px-4 sm:py-3">
        <div className="flex items-start gap-3">
          <StepNumberBadge number={status.step.number} complete={false} />
          <Icon name="exclamation-triangle" size="md" className="shrink-0 mt-0.5 text-amber-500" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium text-text">{status.step.question}</span>
              <nldd-link href={status.step.kcbrUrl} target="_blank" accessible-label="Bekijk op KCBR" start-icon="external-link" />
            </div>
            <p className="text-xs text-text-secondary mt-0.5">{status.step.description}</p>
          </div>
        </div>
        <div className="mt-2 ml-9 sm:ml-10 space-y-1.5">
          <StepTypeGroups
            status={status}
            onCreateNew={onCreateNew}
            onLinkExisting={onLinkExisting}
          />
          <KompasStepSuggestions
            dossierId={dossierId}
            stepNodeTypes={status.step.nodeTypes}
            stepDescription={status.step.question}
          />
        </div>
      </div>
    </div>
  );
}

interface BeleidskompasPanelProps {
  nodeId: string;
  stakeholderCount: number;
  onNavigateToStakeholders: () => void;
}

export function BeleidskompasPanel({ nodeId, stakeholderCount, onNavigateToStakeholders }: BeleidskompasPanelProps) {
  const { data: graphData, isLoading, isError } = useNodeGraph(nodeId, 1);
  const { steps, completedCount, totalSteps } = useCompletenessAnalysis(graphData, nodeId);
  const [linkModalType, setLinkModalType] = useState<NodeType | null>(null);
  const [createModalType, setCreateModalType] = useState<NodeType | null>(null);

  // Collect IDs of nodes already linked to this dossier via onderdeel_van
  const linkedNodeIds = useMemo(() => {
    if (!graphData) return new Set<string>();
    const ids = new Set<string>();
    for (const edge of graphData.edges) {
      if (edge.edge_type_id === EDGE_TYPE_ONDERDEEL_VAN && edge.to_node_id === nodeId) {
        ids.add(edge.from_node_id);
      }
    }
    return ids;
  }, [graphData, nodeId]);

  if (isLoading) {
    return (
      <Card>
        <div className="px-4 py-6 text-center text-sm text-text-secondary">
          Beleidskompas laden...
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <div className="px-4 py-6 text-center text-sm text-text-secondary">
          Beleidskompas kon niet geladen worden.
        </div>
      </Card>
    );
  }

  return (
    <>
      <Card>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Icon name="signpost" size="md" className="text-primary-700 shrink-0" />
            <h3 className="text-sm font-semibold text-text">Beleidskompas</h3>
            <nldd-link href={KCBR_MAIN_URL} target="_blank" accessible-label="Bekijk Beleidskompas op KCBR" start-icon="external-link" />
          </div>
          <div className="w-32">
            <nldd-progress-bar
              value={completedCount}
              max={totalSteps}
              color="success"
              size="sm"
              value-text={`${completedCount}/${totalSteps}`}
            />
          </div>
        </div>

        {/* Stakeholders reference (recurring question) — only shown when stakeholders exist */}
        {stakeholderCount > 0 && (
          <div className="mb-3">
            <nldd-inline-dialog
              icon="users"
              text="Wie zijn belanghebbenden?"
              horizontal-alignment="left"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <ActionLink text={`${stakeholderCount} betrokkenen`} onClick={onNavigateToStakeholders} />
                <nldd-link href={KCBR_STAKEHOLDERS_URL} target="_blank" accessible-label="Bekijk op KCBR" start-icon="external-link" size="xs" />
              </div>
            </nldd-inline-dialog>
          </div>
        )}

        {/* Steps */}
        <div className="rounded-lg border border-border overflow-hidden">
          {steps.map((stepStatus) => (
            <BeleidskompasStepRow
              key={stepStatus.step.id}
              status={stepStatus}
              dossierId={nodeId}
              onCreateNew={(nodeType) => setCreateModalType(nodeType)}
              onLinkExisting={(nodeType) => setLinkModalType(nodeType)}
            />
          ))}
        </div>

        {/* Gap Analysis */}
        <div className="mt-4 pt-4 border-t border-border">
          <GapAnalysisPanel dossierId={nodeId} />
        </div>
      </Card>

      {linkModalType && (
        <LinkExistingNodeModal
          open={!!linkModalType}
          onClose={() => setLinkModalType(null)}
          dossierId={nodeId}
          nodeType={linkModalType}
          excludeNodeIds={linkedNodeIds}
        />
      )}

      {createModalType && (
        <NodeCreateForm
          open={!!createModalType}
          onClose={() => setCreateModalType(null)}
          defaultNodeType={createModalType}
          linkToDossierId={nodeId}
        />
      )}
    </>
  );
}
