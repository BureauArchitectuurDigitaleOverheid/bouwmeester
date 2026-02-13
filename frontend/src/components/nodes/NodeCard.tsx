import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, Link as LinkIcon } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import type { CorpusNode, NodeStatus } from '@/types';
import { NODE_TYPE_COLORS, NODE_STATUS_LABELS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { richTextToPlain } from '@/utils/richtext';
import { formatDateShort } from '@/utils/dates';

interface NodeCardProps {
  node: CorpusNode;
}

export function NodeCard({ node }: NodeCardProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { nodeLabel, nodeAltLabel } = useVocabulary();
  const color = NODE_TYPE_COLORS[node.node_type];

  return (
    <Card
      hoverable
      onClick={() => navigate(`/nodes/${node.id}`, { state: { fromCorpus: location.pathname + location.search } })}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={color as 'blue'} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && (
              <Badge variant="gray">{NODE_STATUS_LABELS[node.status as NodeStatus] ?? node.status}</Badge>
            )}
          </div>

          <h3 className="text-sm font-semibold text-text truncate mb-1">
            {node.title}
          </h3>

          {node.description && (
            <p className="text-xs text-text-secondary line-clamp-2">
              {richTextToPlain(node.description)}
            </p>
          )}
        </div>

        <ArrowRight className="h-4 w-4 text-text-secondary shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>

      {/* Footer info */}
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border">
        {node.edge_count !== undefined && (
          <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
            <LinkIcon className="h-3 w-3" />
            {node.edge_count} verbindingen
          </span>
        )}
        <span className="text-xs text-text-secondary ml-auto">
          {formatDateShort(node.updated_at ?? node.created_at)}
        </span>
      </div>
    </Card>
  );
}
