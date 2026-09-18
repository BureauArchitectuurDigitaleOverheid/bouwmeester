import { isPersonOnline } from '@/utils/people';

/** nldd-avatar only accepts spacer-aligned pixel sizes. */
type AvatarSize = '24' | '28' | '32' | '40' | '44' | '48';

interface PersonAvatarProps {
  person: { naam: string; is_agent: boolean; last_seen_at?: string | null };
  /** A size from the spacer-aligned set nldd-avatar accepts. Defaults to '40'. */
  size?: AvatarSize;
}

/**
 * `nldd-avatar` behind the previous API.
 *
 * The element derives initials from `name` itself and falls back to an icon
 * when there is nothing to derive (an empty name) or when `icon` is set
 * explicitly, which is what marks an agent here — 'sparkles' rather than a
 * literal robot glyph, matching the lucide->nldd icon bridge's own choice for
 * `Bot`. The online dot is `nldd-badge`, the design system's small
 * count/status overlay: icon-only with no text or number, it renders as a
 * plain dot, and `pulse` gives it the "live" read a static ring used to
 * imply.
 */
export function PersonAvatar({ person, size = '40' }: PersonAvatarProps) {
  const online = isPersonOnline(person);

  return (
    <div className="relative shrink-0" style={{ width: `${size}px`, height: `${size}px` }}>
      <nldd-avatar
        name={person.naam}
        size={size}
        {...(person.is_agent ? { icon: 'sparkles', color: 'inherit' } : {})}
      />
      {online && (
        <nldd-badge
          color="success"
          icon="circle-filled-extra-small"
          pulse
          decorative
          className="absolute bottom-0 right-0"
        />
      )}
    </div>
  );
}
