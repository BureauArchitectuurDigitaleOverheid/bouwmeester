import { useRef } from 'react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Icon } from '@/components/nldd/Icon';
import { useNlddEvent } from '@/components/nldd/events';
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

interface ContactLinkProps {
  href: string;
  text: string;
  startIcon: string;
}

/**
 * `nldd-link` for a contact detail (email, phone) inside a card that is
 * itself clickable. The click bubbles same as a native anchor would, so it
 * is stopped here before it reaches the card's own open-detail handler.
 */
function ContactLink({ href, text, startIcon }: ContactLinkProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', (e) => e.stopPropagation());
  return (
    <nldd-link ref={ref} href={href} text={text} start-icon={startIcon} size="xs" />
  );
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
      {/* nldd-identity lays out its own avatars/text/supporting-text slots
          side by side, so this needs no wrapping flex container. */}
      <nldd-identity text={person.naam}>
        {/* The avatar composes its own online dot, so it is slotted rather
            than left to nldd-identity's avatar-src (which only takes an
            image). */}
        <div slot="avatars">
          <PersonAvatar person={person} />
        </div>
        {person.is_agent && (
          <nldd-container slot="text" layout="row" gap="8" vertical-alignment="center">
            <nldd-text>{person.naam}</nldd-text>
            <Badge variant="purple">Agent</Badge>
          </nldd-container>
        )}
        <nldd-container slot="supporting-text" gap="4">
          {email && <ContactLink href={`mailto:${email}`} text={email} startIcon="envelope" />}
          {person.default_phone && (
            <ContactLink href={`tel:${person.default_phone}`} text={person.default_phone} startIcon="at" />
          )}
          {person.functie && (
            <nldd-container layout="row" gap="6" vertical-alignment="center">
              <Icon name="Briefcase" size="xs" />
              <nldd-text size="xs" color="secondary">{formatFunctie(person.functie)}</nldd-text>
            </nldd-container>
          )}
          {person.expertise && (
            <nldd-container layout="row" gap="6" vertical-alignment="center">
              <Icon name="Tag" size="xs" />
              <nldd-text size="xs" color="secondary">{person.expertise}</nldd-text>
            </nldd-container>
          )}
          {person.is_agent && person.description && (
            <nldd-text size="xs" color="secondary">{richTextToPlain(person.description)}</nldd-text>
          )}
        </nldd-container>
      </nldd-identity>
    </Card>
  );
}
