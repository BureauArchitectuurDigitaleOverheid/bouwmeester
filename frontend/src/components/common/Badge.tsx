import type { EntityColor } from '@/types';

/**
 * A labelled chip, as an `nldd-tag`.
 *
 * nldd-tag accepts the five semantic roles AND the Rijkshuisstijl colors, so
 * this app's twelve entity colors stay distinct rather than collapsing into
 * five. A color that carries meaning (rood = error, mosgroen = done, geel =
 * attention) maps to the semantic role, which keeps it correct in dark mode and
 * for colorblind users; the purely decorative ones paint as themselves.
 *
 * `nldd-badge` is a different component: a small count or status dot on top of
 * another element, not a labelled chip. Our Badge is a chip, hence the tag.
 */
type TagColor = NonNullable<React.ComponentProps<'nldd-tag'>['color']>;

const TAG_COLOR: Record<EntityColor, TagColor> = {
  // Semantic: these carry meaning, so they follow the roles.
  rood: 'critical',
  groen: 'success',
  mosgroen: 'success',
  geel: 'warning',
  oranje: 'warning',
  lintblauw: 'accent',
  coolgray: 'neutral',
  donkerblauw: 'neutral',
  // Decorative: the Rijkshuisstijl color itself.
  paars: 'paars',
  hemelblauw: 'hemelblauw',
  roze: 'roze',
  violet: 'violet',
};

interface BadgeProps {
  children: React.ReactNode;
  color?: EntityColor;
  dot?: boolean;
  className?: string;
  title?: string;
}

export function Badge({ children, color = 'coolgray', dot = false, className, title }: BadgeProps) {
  // The element takes its label as an attribute; children only work through the
  // text slot. Most call sites pass a plain string, so prefer the attribute and
  // fall back to the slot for rich content.
  const text = typeof children === 'string' ? children : undefined;

  return (
    <nldd-tag
      color={TAG_COLOR[color]}
      size="sm"
      className={className}
      title={title}
      {...(text ? { text } : {})}
      {...(dot ? { icon: 'circle-filled-extra-small' } : {})}
    >
      {text ? null : children}
    </nldd-tag>
  );
}
