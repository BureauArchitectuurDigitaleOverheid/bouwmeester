import { AlertTriangle } from 'lucide-react';
import { useLeadMetrics } from '@/hooks/useLeads';
import { LEAD_STAGE_ORDER, LEAD_STAGE_LABELS, LEAD_STAGE_COLORS } from '@/types';

export function LeadMetricsBar() {
  const { data: metrics } = useLeadMetrics();

  if (!metrics) return null;

  return (
    <div className="flex items-center gap-3 flex-wrap text-sm">
      <span className="font-medium text-text">
        {metrics.total} {metrics.total === 1 ? 'lead' : 'leads'}
      </span>

      <span className="text-border">|</span>

      {LEAD_STAGE_ORDER.map((stage) => {
        const count = metrics.by_stage[stage] ?? 0;
        if (count === 0) return null;
        return (
          <span
            key={stage}
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${LEAD_STAGE_COLORS[stage]}`}
          >
            {LEAD_STAGE_LABELS[stage]}: {count}
          </span>
        );
      })}

      {metrics.stale_count > 0 && (
        <>
          <span className="text-border">|</span>
          <span className="inline-flex items-center gap-1 text-xs text-red-600 font-medium">
            <AlertTriangle className="h-3.5 w-3.5" />
            {metrics.stale_count} inactief
          </span>
        </>
      )}
    </div>
  );
}
