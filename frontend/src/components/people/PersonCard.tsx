import { Mail, Briefcase, Phone } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { PersonAvatar } from '@/components/people/PersonAvatar';
import { formatFunctie } from '@/types';
import type { Person } from '@/types';

interface PersonCardProps {
  person: Person;
  onClick?: (person: Person) => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent, person: Person) => void;
}

export function PersonCard({ person, onClick, draggable, onDragStart }: PersonCardProps) {
  return (
    <Card
      hoverable
      onClick={onClick ? () => onClick(person) : undefined}
      draggable={draggable}
      onDragStart={onDragStart ? (e: React.DragEvent) => onDragStart(e, person) : undefined}
    >
      <div className="flex items-start gap-3">
        <PersonAvatar person={person} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text truncate">
              {person.naam}
            </h3>
            {person.is_agent && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-100 text-purple-700">
                Agent
              </span>
            )}
          </div>

          <div className="space-y-1 mt-1.5">
            {(person.default_email || person.email) && (
              <a
                href={`mailto:${person.default_email || person.email}`}
                className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary-600 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <Mail className="h-3 w-3 shrink-0" />
                <span className="truncate">{person.default_email || person.email}</span>
              </a>
            )}
            {person.default_phone && (
              <a
                href={`tel:${person.default_phone}`}
                className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary-600 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <Phone className="h-3 w-3 shrink-0" />
                <span className="truncate">{person.default_phone}</span>
              </a>
            )}
            {person.functie && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Briefcase className="h-3 w-3 shrink-0" />
                <span className="truncate">{formatFunctie(person.functie)}</span>
              </div>
            )}
            {person.is_agent && person.description && (
              <p className="text-xs text-text-secondary truncate">{person.description}</p>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
