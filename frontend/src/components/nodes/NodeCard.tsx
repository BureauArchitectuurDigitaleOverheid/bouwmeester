import { useNavigate, useLocation } from 'react-router-dom';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Icon } from '@/components/nldd/Icon';
import type { CorpusNode, NodeStatus } from '@/types';
import { NODE_TYPE_COLORS, NODE_STATUS_LABELS, NodeType } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { richTextToPlain } from '@/utils/richtext';
import { formatDateShort } from '@/utils/dates';
import { formatCurrency, formatCurrencyCompact } from '@/utils/format';

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
            <Badge variant={color} dot title={nodeAltLabel(node.node_type)}>
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

        <Icon name="arrow-right" size="md" className="shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>

      {/* Footer info */}
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border">
        {node.edge_count !== undefined && (
          <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
            <Icon name="link" size="xs" />
            {node.edge_count} verbindingen
          </span>
        )}
        {node.financieel_summary && node.financieel_summary.totaal_budget > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-text-secondary" title={`Budget: ${formatCurrency(node.financieel_summary.totaal_budget)} — Gerealiseerd: ${formatCurrency(node.financieel_summary.totaal_gerealiseerd)}`}>
            <Icon name="euro-sign" size="xs" />
            {formatCurrencyCompact(node.financieel_summary.totaal_budget)}
          </span>
        )}
        {node.node_type === NodeType.DOSSIER && node.beleidskompas_progress && (
          <span
            className={`inline-flex items-center gap-1 text-xs font-medium ${
              node.beleidskompas_progress.completed_steps === node.beleidskompas_progress.total_steps
                ? 'text-emerald-600'
                : 'text-text-secondary'
            }`}
            title={`Beleidskompas: ${node.beleidskompas_progress.completed_steps} van ${node.beleidskompas_progress.total_steps} stappen compleet`}
          >
            <Icon name="signpost" size="xs" />
            {node.beleidskompas_progress.completed_steps}/{node.beleidskompas_progress.total_steps}
          </span>
        )}
        <span className="text-xs text-text-secondary ml-auto">
          {formatDateShort(node.updated_at ?? node.created_at)}
        </span>
      </div>
    </Card>
  );
}
