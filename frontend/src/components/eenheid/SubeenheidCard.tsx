import { Building2, AlertTriangle } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { ORGANISATIE_TYPE_LABELS } from '@/types';
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
            <Building2 className="h-4 w-4 text-text-secondary shrink-0" />
            <div>
              <p className="font-medium text-text">{sub.eenheid_naam}</p>
              <p className="text-xs text-text-secondary">
                {ORGANISATIE_TYPE_LABELS[sub.eenheid_type] ?? sub.eenheid_type}
              </p>
            </div>
          </div>
          {sub.overdue_count > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
              <AlertTriangle className="h-3 w-3" />
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
