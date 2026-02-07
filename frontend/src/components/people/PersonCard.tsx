import { User, Mail, Building, Briefcase, Shield } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { ROL_LABELS } from '@/types';
import type { Person } from '@/types';

interface PersonCardProps {
  person: Person;
  onClick?: (person: Person) => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent, person: Person) => void;
}

export function PersonCard({ person, onClick, draggable, onDragStart }: PersonCardProps) {
  const initials = person.naam
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <Card
      hoverable
      onClick={onClick ? () => onClick(person) : undefined}
      draggable={draggable}
      onDragStart={onDragStart ? (e: React.DragEvent) => onDragStart(e, person) : undefined}
    >
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary-100 text-primary-700 font-semibold text-sm shrink-0">
          {initials || <User className="h-5 w-5" />}
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-text truncate">
            {person.naam}
          </h3>

          <div className="space-y-1 mt-1.5">
            {person.email && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Mail className="h-3 w-3 shrink-0" />
                <span className="truncate">{person.email}</span>
              </div>
            )}
            {person.afdeling && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Building className="h-3 w-3 shrink-0" />
                <span className="truncate">{person.afdeling}</span>
              </div>
            )}
            {person.functie && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Briefcase className="h-3 w-3 shrink-0" />
                <span className="truncate">{person.functie}</span>
              </div>
            )}
            {person.rol && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Shield className="h-3 w-3 shrink-0" />
                <span className="truncate">{ROL_LABELS[person.rol] || person.rol}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
