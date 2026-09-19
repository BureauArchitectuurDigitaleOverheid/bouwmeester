import { useLeadMetrics } from '@/hooks/useLeads';
import { LEAD_STAGE_ORDER, LEAD_STAGE_LABELS } from '@/types';
import { stageTagColor } from './stageColors';

export function LeadMetricsBar() {
  const { data: metrics } = useLeadMetrics();

  if (!metrics) return null;

  return (
    <nldd-container layout="wrap" gap="12" vertical-alignment="center">
      <nldd-text size="sm" weight="medium">
        {metrics.total} {metrics.total === 1 ? 'lead' : 'leads'}
      </nldd-text>

      {LEAD_STAGE_ORDER.map((stage) => {
        const count = metrics.by_stage[stage] ?? 0;
        if (count === 0) return null;
        return (
          <nldd-tag key={stage} color={stageTagColor(stage)} size="sm" text={`${LEAD_STAGE_LABELS[stage]}: ${count}`} />
        );
      })}

      {metrics.stale_count > 0 && (
        <nldd-container layout="row" gap="4" vertical-alignment="center">
          <nldd-icon name="exclamation-triangle" size="16" aria-hidden="true" />
          <nldd-text size="xs" weight="medium" color="critical">
            {metrics.stale_count} inactief
          </nldd-text>
        </nldd-container>
      )}
    </nldd-container>
  );
}
