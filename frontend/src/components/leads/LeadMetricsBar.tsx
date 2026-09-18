import { useLeadMetrics } from '@/hooks/useLeads';
import { LEAD_STAGE_ORDER, LEAD_STAGE_LABELS, LEAD_STAGE_COLORS } from '@/types';

export function LeadMetricsBar() {
  const { data: metrics } = useLeadMetrics();

  if (!metrics) return null;

  return (
    <div className="flex items-center gap-3 flex-wrap text-sm">
      <nldd-text size="sm" weight="medium">
        {metrics.total} {metrics.total === 1 ? 'lead' : 'leads'}
      </nldd-text>

      <span className="text-border">|</span>

      {/* LEAD_STAGE_COLORS holds raw Tailwind chip classes for seven stages,
          not one of the five semantic roles; collapsing them would lose the
          per-stage distinctness, and src/types is off-limits to edit in this
          pass. The chip stays a styled span rather than an nldd-tag with a
          guessed color. */}
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
          <nldd-text size="xs" weight="medium" color="critical" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
            <nldd-icon name="exclamation-triangle" size="16" aria-hidden="true" />
            {metrics.stale_count} inactief
          </nldd-text>
        </>
      )}
    </div>
  );
}
