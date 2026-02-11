import { User, Mail, Briefcase, Bot } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { formatFunctie } from '@/types';
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
        {person.is_agent ? (
          <div className="flex items-center justify-center h-10 w-10 rounded-full bg-purple-100 text-purple-700 shrink-0">
            <Bot className="h-5 w-5" />
          </div>
        ) : (
          <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary-100 text-primary-700 font-semibold text-sm shrink-0">
            {initials || <User className="h-5 w-5" />}
          </div>
        )}

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
            {person.email && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Mail className="h-3 w-3 shrink-0" />
                <span className="truncate">{person.email}</span>
              </div>
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
