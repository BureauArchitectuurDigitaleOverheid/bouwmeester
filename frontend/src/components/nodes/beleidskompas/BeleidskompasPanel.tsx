import { useState } from 'react';
import { CheckCircle2, AlertTriangle, ChevronDown, ChevronRight, Plus, Link as LinkIcon } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { useNodeGraph } from '@/hooks/useNodes';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useCompletenessAnalysis, type StepStatus } from './useCompletenessAnalysis';
import { LinkExistingNodeModal } from './LinkExistingNodeModal';
import { NodeCreateForm } from '../NodeCreateForm';
import { NODE_TYPE_LABELS, NODE_TYPE_COLORS, type NodeType } from '@/types';

interface BeleidskompasStepRowProps {
  status: StepStatus;
  dossierId: string;
  onCreateNew: (nodeType: NodeType) => void;
  onLinkExisting: (nodeType: NodeType) => void;
}

function BeleidskompasStepRow({ status, dossierId, onCreateNew, onLinkExisting }: BeleidskompasStepRowProps) {
  const [expanded, setExpanded] = useState(false);
  const { openNodeDetail } = useNodeDetail();

  if (status.isComplete) {
    return (
      <div className="border-b border-border last:border-b-0">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-3 w-full px-4 py-3 text-left hover:bg-gray-50/50 transition-colors"
        >
          <CheckCircle2 className="h-4.5 w-4.5 text-emerald-500 shrink-0" />
          <span className="text-sm font-medium text-text flex-1">{status.step.label}</span>
          <span className="text-xs text-text-secondary mr-2">
            {status.count} {NODE_TYPE_LABELS[status.step.nodeType].toLowerCase()}
            {status.count !== 1 ? 's' : ''}
          </span>
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-text-secondary" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-secondary" />
          )}
        </button>
        {expanded && (
          <div className="px-4 pb-3 space-y-1.5 ml-7">
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
            <div className="flex items-center gap-2 pt-1">
              <Button
                variant="ghost"
                size="sm"
                icon={<Plus className="h-3.5 w-3.5" />}
                onClick={() => onCreateNew(status.step.nodeType)}
              >
                Nieuw aanmaken
              </Button>
              <Button
                variant="ghost"
                size="sm"
                icon={<LinkIcon className="h-3.5 w-3.5" />}
                onClick={() => onLinkExisting(status.step.nodeType)}
              >
                Bestaand koppelen
              </Button>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="border-b border-border last:border-b-0">
      <div className="flex items-center gap-3 px-4 py-3">
        <AlertTriangle className="h-4.5 w-4.5 text-amber-500 shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium text-text">{status.step.label}</span>
          <p className="text-xs text-text-secondary mt-0.5">{status.step.description}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="sm"
            icon={<Plus className="h-3.5 w-3.5" />}
            onClick={() => onCreateNew(status.step.nodeType)}
          >
            Nieuw
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<LinkIcon className="h-3.5 w-3.5" />}
            onClick={() => onLinkExisting(status.step.nodeType)}
          >
            Koppelen
          </Button>
        </div>
      </div>
    </div>
  );
}

interface BeleidskompansPanelProps {
  nodeId: string;
}

export function BeleidskompasPanel({ nodeId }: BeleidskompansPanelProps) {
  const { data: graphData, isLoading } = useNodeGraph(nodeId, 2);
  const { steps, completedCount, totalSteps } = useCompletenessAnalysis(graphData, nodeId);
  const [linkModalType, setLinkModalType] = useState<NodeType | null>(null);
  const [createModalType, setCreateModalType] = useState<NodeType | null>(null);

  if (isLoading) {
    return (
      <Card>
        <div className="px-4 py-6 text-center text-sm text-text-secondary">
          Beleidskompas laden...
        </div>
      </Card>
    );
  }

  const progressPercent = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;

  return (
    <>
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-text">Beleidskompas</h3>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <div className="w-24 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="text-xs font-medium text-text-secondary">
                {completedCount}/{totalSteps} stappen
              </span>
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-border overflow-hidden">
          {steps.map((status) => (
            <BeleidskompasStepRow
              key={status.step.id}
              status={status}
              dossierId={nodeId}
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
