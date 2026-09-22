import { useRef, type ReactNode, type HTMLAttributes } from 'react';
import { useNlddEvent } from '@/components/nldd/events';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  hoverable?: boolean;
  padding?: boolean;
  /**
   * Names the action when the whole card is one control, which also makes it
   * one: `nldd-card` gets its `button` attribute, and with it a real button in
   * the shadow root, a tab stop, and Enter/Space.
   *
   * Leave it off when the card holds its own buttons. Nesting a control inside
   * a button is invalid, and the inner control is what should be operable.
   */
  actionLabel?: string;
}

/**
 * A surface, optionally with a header and a footer.
 *
 * `hoverable` is only the pointer cursor: it says "this looks clickable"
 * without making it so, which leaves a card operable by mouse, unreachable by
 * tab and unannounced to a screen reader. Use `actionLabel` when the whole card
 * is one action; it makes the card a real button.
 *
 * The two are separate because a card that contains buttons cannot become one,
 * so the choice belongs to the call site rather than to the presence of an
 * `onClick`.
 */
export function Card({
  children,
  header,
  footer,
  hoverable = false,
  padding = true,
  actionLabel,
  className,
  style,
  onClick,
  ...props
}: CardProps) {
  // The listener goes on the element, always, not on a React onClick.
  //
  // With `button` the activation happens on a <button> inside the shadow root
  // and arrives as a composed click on the host, which React's synthetic
  // system does not deliver. Without `button` it is no better: an `onClick`
  // spread onto a custom element is not wired as a plain DOM listener either,
  // which is why the task cards never opened anything on click.
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(
    ref,
    'click',
    onClick
      ? (event) => onClick(event as unknown as React.MouseEvent<HTMLDivElement>)
      : undefined,
  );

  return (
    <nldd-card
      ref={ref}
      className={className}
      {...(actionLabel ? { button: true, 'accessible-label': actionLabel } : {})}
      // Merged, not replaced: `...props` spreading a caller's `style` after
      // this line would drop the pointer cursor, and setting it here without
      // merging would drop the caller's. With `button` the element brings its
      // own cursor, so this only covers the visual-only case.
      style={{ ...(hoverable && !actionLabel ? { cursor: 'pointer' } : {}), ...style }}
      {...props}
    >
      {header && <div slot="header">{header}</div>}
      {/* nldd-card draws the surface but has no inset of its own, by design, so
          a container owns the spacing: 12px all round, 20/16 from sm. */}
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
