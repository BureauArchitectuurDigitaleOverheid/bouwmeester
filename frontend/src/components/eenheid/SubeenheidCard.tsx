import { Card } from '@/components/common/Card';
import { Icon } from '@/components/nldd/Icon';
import { formatOrganisatieType } from '@/types';
import type { EenheidSubeenheidStats } from '@/types';

interface SubeenheidCardProps {
  sub: EenheidSubeenheidStats;
  onSelect: (eenheidId: string) => void;
}

export function SubeenheidCard({ sub, onSelect }: SubeenheidCardProps) {
  return (
    <Card hoverable onClick={() => onSelect(sub.eenheid_id)}>
      <div className="space-y-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Icon name="Building2" size="md" className="text-text-secondary" />
            <div>
              <p className="font-medium text-text">{sub.eenheid_naam}</p>
              <p className="text-xs text-text-secondary">
                {formatOrganisatieType(sub.eenheid_type)}
              </p>
            </div>
          </div>
          {sub.overdue_count > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
              <Icon name="AlertTriangle" size="xs" />
              {sub.overdue_count}
            </span>
          )}
        </div>
        <div className="flex gap-4 text-sm text-text-secondary">
          <span>Open: {sub.open_count}</span>
          <span>In uitvoering: {sub.in_progress_count}</span>
          <span>Afgerond: {sub.done_count}</span>
        </div>
      </div>
    </Card>
  );
}
