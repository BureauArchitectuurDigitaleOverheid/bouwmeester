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
      // Only a button when there is something to activate. Without a handler
      // it is a card that happens to be draggable, and announcing it as a
      // button would be the fake-affordance this codebase already fixed once.
      {...(onClick ? { actionLabel: person.naam } : { hoverable: false })}
      onClick={onClick ? () => onClick(person) : undefined}
      draggable={draggable}
      onDragStart={onDragStart ? (e: React.DragEvent) => onDragStart(e, person) : undefined}
    >
      {/*
        The identity carries the avatar and the name; the details sit under it
        rather than inside its `supporting-text` slot.

        Measured: that slot is a flex column sized by its content, with no
        `flex: 1`. An nldd-container slotted into it is a block with no
        intrinsic width, so the column had nothing to measure and collapsed to
        zero. The name then wrapped after every word and the card grew from 63
        to 182 pixels tall. An identity with plain attributes measures 456px in
        the same card, so the component was fine and the markup was not.

        The slots take rich text (a link, a <time>), not a layout of their own.
      */}
      <nldd-container gap="8">
        <nldd-identity text={person.naam}>
          {/* The avatar composes its own online dot, so it is slotted rather
              than left to nldd-identity's avatar-src (which only takes an
              image). */}
          <div slot="avatars">
            <PersonAvatar person={person} />
          </div>
          {person.is_agent && (
            <span slot="text">
              {person.naam} <Badge variant="purple">Agent</Badge>
            </span>
          )}
        </nldd-identity>

        <nldd-container gap="4">
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
      </nldd-container>
    </Card>
  );
}
