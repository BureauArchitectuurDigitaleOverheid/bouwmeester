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
  ...props
}: CardProps) {
  return (
    <nldd-card
      className={className}
      style={hoverable ? { cursor: 'pointer' } : undefined}
      {...props}
    >
      {header && <div slot="header">{header}</div>}
      {padding ? <div className="px-3 py-3 sm:px-5 sm:py-4">{children}</div> : children}
      {footer && <div slot="footer">{footer}</div>}
    </nldd-card>
  );
}
