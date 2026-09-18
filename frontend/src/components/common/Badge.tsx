import type { BadgeVariant } from '@/types';

/**
 * `nldd-tag` behind the previous Badge API.
 *
 * nldd-tag accepts the five semantic roles AND the Rijkshuisstijl colors, so the
 * twelve variants this app uses keep their distinctness instead of collapsing
 * into five. Where a variant already carried meaning (red = error, emerald =
 * done, amber = attention) it maps to the semantic role, which keeps it correct
 * in dark mode and for colorblind users; the purely decorative ones map to the
 * nearest Rijkshuisstijl color.
 *
 * `nldd-badge` is a different component: a small count or status dot on top of
 * another element, not a labelled chip. Our Badge is a chip, hence the tag.
 */
type TagColor = NonNullable<React.ComponentProps<'nldd-tag'>['color']>;

const VARIANT_COLORS: Record<BadgeVariant, TagColor> = {
  // Semantic: these carry meaning, so they follow the roles.
  red: 'critical',
  green: 'success',
  emerald: 'success',
  amber: 'warning',
  orange: 'warning',
  blue: 'accent',
  gray: 'neutral',
  slate: 'neutral',
  // Decorative: nearest Rijkshuisstijl color.
  purple: 'paars',
  cyan: 'hemelblauw',
  rose: 'roze',
  indigo: 'donkerblauw',
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  dot?: boolean;
  className?: string;
  title?: string;
}

export function Badge({ children, variant = 'gray', dot = false, className, title }: BadgeProps) {
  // The element takes its label as an attribute; children only work through the
  // text slot. Most call sites pass a plain string, so prefer the attribute and
  // fall back to the slot for rich content.
  const text = typeof children === 'string' ? children : undefined;

  return (
    <nldd-tag
      color={VARIANT_COLORS[variant]}
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
