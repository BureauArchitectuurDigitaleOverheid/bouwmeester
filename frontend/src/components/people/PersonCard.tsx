import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Icon } from '@/components/nldd/Icon';
import { PersonAvatar } from '@/components/people/PersonAvatar';
import { formatFunctie } from '@/types';
import { richTextToPlain } from '@/utils/richtext';
import type { Person } from '@/types';

interface PersonCardProps {
  person: Person;
  onClick?: (person: Person) => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent, person: Person) => void;
}

export function PersonCard({ person, onClick, draggable, onDragStart }: PersonCardProps) {
  const email = person.default_email || person.email;

  return (
    <Card
      hoverable
      onClick={onClick ? () => onClick(person) : undefined}
      draggable={draggable}
      onDragStart={onDragStart ? (e: React.DragEvent) => onDragStart(e, person) : undefined}
    >
      <div className="flex items-start gap-3">
        {/* The avatar composes its own online dot, so it is slotted rather
            than left to nldd-identity's avatar-src (which only takes an
            image). */}
        <div slot="avatars">
          <PersonAvatar person={person} />
        </div>
        <nldd-identity text={person.naam} className="flex-1 min-w-0">
          {person.is_agent && (
            <span slot="text" className="inline-flex items-center gap-2">
              {person.naam}
              <Badge variant="purple">Agent</Badge>
            </span>
          )}
          <div slot="supporting-text" className="space-y-1 mt-1">
            {email && (
              <a
                href={`mailto:${email}`}
                className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary-600 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <Icon name="Mail" size="xs" />
                <span className="truncate">{email}</span>
              </a>
            )}
            {person.default_phone && (
              <a
                href={`tel:${person.default_phone}`}
                className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary-600 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <Icon name="Phone" size="xs" />
                <span className="truncate">{person.default_phone}</span>
              </a>
            )}
            {person.functie && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Icon name="Briefcase" size="xs" />
                <span className="truncate">{formatFunctie(person.functie)}</span>
              </div>
            )}
            {person.expertise && (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Icon name="Tag" size="xs" />
                <span className="truncate">{person.expertise}</span>
              </div>
            )}
            {person.is_agent && person.description && (
              <p className="text-xs text-text-secondary truncate">{richTextToPlain(person.description)}</p>
            )}
          </div>
        </nldd-identity>
      </div>
    </Card>
  );
}
