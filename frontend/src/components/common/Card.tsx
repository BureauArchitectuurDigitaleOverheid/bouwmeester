import type { ReactNode, HTMLAttributes } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  hoverable?: boolean;
  padding?: boolean;
}

/**
 * `nldd-card` behind the previous API, so existing call sites are unchanged.
 *
 * `hoverable` used to mean "looks clickable". The card has a real `button`
 * attribute for that, which also gives it the keyboard and ARIA of a control —
 * but only when the whole card is genuinely one action. Several call sites put
 * their own buttons inside a hoverable card, and nesting controls would be
 * invalid, so this keeps `hoverable` purely visual and leaves the click handling
 * where it already is.
 */
export function Card({
  children,
  header,
  footer,
  hoverable = false,
  padding = true,
  className,
  style,
  ...props
}: CardProps) {
  return (
    <nldd-card
      className={className}
      // Merged, not replaced: `...props` spreading a caller's `style` after
      // this line would drop the pointer cursor, and setting it here without
      // merging would drop the caller's.
      style={{ ...(hoverable ? { cursor: 'pointer' } : {}), ...style }}
      {...props}
    >
      {header && <div slot="header">{header}</div>}
      {/* nldd-card draws the surface but has no inset of its own, by design, so
          a container owns the spacing. The sm-* variants are the same
          breakpoint the Tailwind version used: 12px all round, 20/16 from sm. */}
      {padding ? (
        <nldd-container
          padding="12"
          sm-padding-inline="20"
          sm-padding-block="16"
        >
          {children}
        </nldd-container>
      ) : (
        children
      )}
      {footer && <div slot="footer">{footer}</div>}
    </nldd-card>
  );
}
