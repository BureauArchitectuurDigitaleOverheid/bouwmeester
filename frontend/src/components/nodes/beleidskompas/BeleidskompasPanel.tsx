import { useState, useMemo } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Plus,
  Link as LinkIcon,
  ExternalLink,
  Users,
} from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { useNodeGraph } from '@/hooks/useNodes';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useCompletenessAnalysis, type StepStatus } from './useCompletenessAnalysis';
import { KCBR_MAIN_URL, KCBR_STAKEHOLDERS_URL } from './config';
import { LinkExistingNodeModal } from './LinkExistingNodeModal';
import { NodeCreateForm } from '../NodeCreateForm';
import { NODE_TYPE_LABELS, NODE_TYPE_COLORS, type NodeType } from '@/types';
import { EDGE_TYPE_ONDERDEEL_VAN } from './constants';

interface StepActionButtonsProps {
  nodeType: NodeType;
  onCreateNew: (nodeType: NodeType) => void;
  onLinkExisting: (nodeType: NodeType) => void;
  compact?: boolean;
}

function StepActionButtons({ nodeType, onCreateNew, onLinkExisting, compact }: StepActionButtonsProps) {
  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="sm"
        icon={<Plus className="h-3.5 w-3.5" />}
        onClick={() => onCreateNew(nodeType)}
      >
        {compact ? null : 'Nieuw'}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        icon={<LinkIcon className="h-3.5 w-3.5" />}
        onClick={() => onLinkExisting(nodeType)}
      >
        {compact ? null : 'Koppelen'}
      </Button>
    </div>
  );
}

interface BeleidskompasStepRowProps {
  status: StepStatus;
  onCreateNew: (nodeType: NodeType) => void;
  onLinkExisting: (nodeType: NodeType) => void;
}

function StepNumberBadge({ number, complete }: { number: number; complete: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center h-6 w-6 rounded-full text-xs font-bold shrink-0 ${
        complete
          ? 'bg-emerald-100 text-emerald-700'
          : 'bg-gray-100 text-gray-500'
      }`}
    >
      {number}
    </span>
  );
}

function BeleidskompasStepRow({ status, onCreateNew, onLinkExisting }: BeleidskompasStepRowProps) {
  const [expanded, setExpanded] = useState(false);
  const { openNodeDetail } = useNodeDetail();
  const isMultiType = status.step.nodeTypes.length > 1;

  if (status.isComplete) {
    return (
      <div className="border-b border-border last:border-b-0">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-3 w-full px-3 py-2.5 sm:px-4 sm:py-3 text-left hover:bg-gray-50/50 transition-colors"
        >
          <StepNumberBadge number={status.step.number} complete />
          <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-text">{status.step.question}</span>
          </div>
          <span className="text-xs text-text-secondary mr-1 hidden sm:inline">
            {status.count} {status.count === 1 ? 'item' : 'items'}
          </span>
          <a
            href={status.step.kcbrUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-text-secondary hover:text-primary-700 transition-colors shrink-0"
            title="Bekijk op KCBR"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-text-secondary shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-secondary shrink-0" />
          )}
        </button>
        {expanded && (
          <div className="px-3 sm:px-4 pb-3 space-y-1.5 ml-9 sm:ml-10">
            {status.nodes.map((node) => (
              <button
                key={node.id}
                onClick={() => openNodeDetail(node.id)}
                className="flex items-center gap-2 w-full p-2 rounded-lg hover:bg-gray-100 transition-colors text-left"
              >
                <Badge variant={NODE_TYPE_COLORS[node.node_type as NodeType]} dot>
                  {NODE_TYPE_LABELS[node.node_type as NodeType]}
                </Badge>
                <span className="text-sm text-text truncate">{node.title}</span>
              </button>
            ))}
            {isMultiType ? (
              <div className="space-y-2 pt-1">
                {status.step.nodeTypes.map((nt) => (
                  <div key={nt} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                    <span className="text-xs text-text-secondary font-medium">
                      {NODE_TYPE_LABELS[nt]}:
                    </span>
                    <StepActionButtons
                      nodeType={nt}
                      onCreateNew={onCreateNew}
                      onLinkExisting={onLinkExisting}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 pt-1">
                <StepActionButtons
                  nodeType={status.step.nodeTypes[0]}
                  onCreateNew={onCreateNew}
                  onLinkExisting={onLinkExisting}
                />
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // Incomplete step
  return (
    <div className="border-b border-border last:border-b-0">
      <div className="px-3 py-2.5 sm:px-4 sm:py-3">
        <div className="flex items-start gap-3">
          <StepNumberBadge number={status.step.number} complete={false} />
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium text-text">{status.step.question}</span>
              <a
                href={status.step.kcbrUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-text-secondary hover:text-primary-700 transition-colors shrink-0"
                title="Bekijk op KCBR"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
            <p className="text-xs text-text-secondary mt-0.5">{status.step.description}</p>
          </div>
        </div>
        {/* Action buttons — stacked on mobile, inline on desktop */}
        <div className="mt-2 ml-9 sm:ml-10">
          {isMultiType ? (
            <div className="space-y-1.5">
              {status.step.nodeTypes.map((nt) => (
                <div key={nt} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                  <span className="text-xs text-text-secondary font-medium min-w-[100px]">
                    {NODE_TYPE_LABELS[nt]}:
                  </span>
                  <StepActionButtons
                    nodeType={nt}
                    onCreateNew={onCreateNew}
                    onLinkExisting={onLinkExisting}
                  />
                </div>
              ))}
            </div>
          ) : (
            <StepActionButtons
              nodeType={status.step.nodeTypes[0]}
              onCreateNew={onCreateNew}
              onLinkExisting={onLinkExisting}
            />
          )}
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

  const progressPercent = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;

  return (
    <>
      <Card>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text">Beleidskompas</h3>
            <a
              href={KCBR_MAIN_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-text-secondary hover:text-primary-700 transition-colors"
              title="Bekijk Beleidskompas op KCBR"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-24 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-xs font-medium text-text-secondary">
              {completedCount}/{totalSteps}
            </span>
          </div>
        </div>

        {/* Stakeholders reference (recurring question) */}
        <div className="mb-3 px-3 py-2 sm:px-4 sm:py-2.5 rounded-lg bg-slate-50 border border-slate-200">
          <div className="flex items-center gap-2 flex-wrap">
            <Users className="h-4 w-4 text-slate-500 shrink-0" />
            <span className="text-xs font-medium text-slate-600">
              Wie zijn belanghebbenden?
            </span>
            <button
              onClick={onNavigateToStakeholders}
              className="text-xs text-primary-700 hover:text-primary-900 transition-colors"
            >
              {stakeholderCount} betrokkenen
            </button>
            <a
              href={KCBR_STAKEHOLDERS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-text-secondary hover:text-primary-700 transition-colors shrink-0"
              title="Bekijk op KCBR"
            >
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>

        {/* Steps */}
        <div className="rounded-lg border border-border overflow-hidden">
          {steps.map((status) => (
            <BeleidskompasStepRow
              key={status.step.id}
              status={status}
              onCreateNew={(nodeType) => setCreateModalType(nodeType)}
              onLinkExisting={(nodeType) => setLinkModalType(nodeType)}
            />
          ))}
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
