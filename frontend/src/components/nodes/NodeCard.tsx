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

  const kompasDone =
    node.beleidskompas_progress &&
    node.beleidskompas_progress.completed_steps === node.beleidskompas_progress.total_steps;

  return (
    <Card
      hoverable
      onClick={() => navigate(`/nodes/${node.id}`, { state: { fromCorpus: location.pathname + location.search } })}
    >
      <nldd-container layout="row" gap="12" vertical-alignment="top">
        <nldd-container gap="4" min-width="0px">
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            <Badge variant={color} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && (
              <Badge variant="gray">{NODE_STATUS_LABELS[node.status as NodeStatus] ?? node.status}</Badge>
            )}
          </nldd-container>

          {/* nldd-text has no truncate/line-clamp prop; that's line-box CSS
              behavior with no token equivalent, so it stays as plain classes. */}
          <h3 className="truncate">
            <nldd-text size="sm" weight="bold">{node.title}</nldd-text>
          </h3>

          {node.description && (
            <p className="line-clamp-2">
              <nldd-text size="xs" color="secondary">{richTextToPlain(node.description)}</nldd-text>
            </p>
          )}
        </nldd-container>

        {/* Hover-reveal: `group-hover-reveal` carries the real CSS (see
            utilities.css), the `group` state comes from Card's hoverable. */}
        <Icon name="arrow-right" size="md" className="shrink-0 group-hover-reveal" />
      </nldd-container>

      {/* Footer info */}
      <nldd-container layout="row" gap="12" vertical-alignment="center" padding-top="12">
        {node.edge_count !== undefined && (
          <nldd-container layout="row" gap="4" vertical-alignment="center">
            <Icon name="link" size="xs" />
            <nldd-text size="xs" color="secondary">{node.edge_count} verbindingen</nldd-text>
          </nldd-container>
        )}
        {node.financieel_summary && node.financieel_summary.totaal_budget > 0 && (
          <nldd-container
            layout="row"
            gap="4"
            vertical-alignment="center"
            title={`Budget: ${formatCurrency(node.financieel_summary.totaal_budget)} — Gerealiseerd: ${formatCurrency(node.financieel_summary.totaal_gerealiseerd)}`}
          >
            <Icon name="euro-sign" size="xs" />
            <nldd-text size="xs" color="secondary">{formatCurrencyCompact(node.financieel_summary.totaal_budget)}</nldd-text>
          </nldd-container>
        )}
        {node.node_type === NodeType.DOSSIER && node.beleidskompas_progress && (
          <nldd-container
            layout="row"
            gap="4"
            vertical-alignment="center"
            title={`Beleidskompas: ${node.beleidskompas_progress.completed_steps} van ${node.beleidskompas_progress.total_steps} stappen compleet`}
          >
            <Icon name="signpost" size="xs" />
            <nldd-text size="xs" weight="medium" color={kompasDone ? 'success' : 'secondary'}>
              {node.beleidskompas_progress.completed_steps}/{node.beleidskompas_progress.total_steps}
            </nldd-text>
          </nldd-container>
        )}
        <nldd-spacer direction="horizontal" size="flexible" />
        <nldd-text size="xs" color="secondary">{formatDateShort(node.updated_at ?? node.created_at)}</nldd-text>
      </nldd-container>
    </Card>
  );
}
