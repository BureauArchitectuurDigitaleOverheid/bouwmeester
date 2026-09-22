/**
 * Router-aware wrappers around the nldd elements that navigate.
 *
 * The design system renders real `<a href>` elements, which is what we want:
 * middle-click and cmd-click keep working, and the address is shareable. But a
 * plain click would do a full page load, so these intercept it and hand the
 * navigation to react-router instead.
 *
 * Clicks are wired with addEventListener rather than an onClick prop because
 * the click originates inside the element's shadow root; React's delegated
 * handler does see it (click bubbles and is composed), but going through
 * useNlddEvent keeps every nldd event binding in this codebase consistent.
 */
import { useCallback, useRef, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNlddEvent } from './events';

/** True when the click asked for something other than plain navigation. */
function isModifiedClick(event: MouseEvent): boolean {
  return (
    event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button === 1
  );
}

interface NlddListItemLinkProps {
  to: string;
  current?: boolean;
  size?: 'sm' | 'md';
  children: ReactNode;
  /** Called after navigation, e.g. to close a sheet on mobile. */
  onNavigate?: () => void;
}

/**
 * An `nldd-list-item` that navigates through the router.
 *
 * Use inside `nldd-list type="navigation"`; `current` puts `aria-current="page"`
 * on the inner anchor.
 */
export function NlddListItemLink({
  to,
  current,
  size = 'md',
  children,
  onNavigate,
}: NlddListItemLinkProps) {
  const ref = useRef<HTMLElement>(null);
  const navigate = useNavigate();

  const onClick = useCallback(
    (event: Event) => {
      const mouse = event as MouseEvent;
      // Let the browser handle cmd/ctrl/shift-click and middle-click itself.
      if (isModifiedClick(mouse)) return;
      event.preventDefault();
      navigate(to);
      onNavigate?.();
    },
    [navigate, to, onNavigate],
  );

  useNlddEvent(ref, 'click', onClick);

  return (
    <nldd-list-item ref={ref} href={to} current={current ? true : undefined} size={size}>
      {children}
    </nldd-list-item>
  );
}

interface NlddButtonProps {
  onClick?: () => void;
  variant?:
    | 'primary'
    | 'secondary'
    | 'destructive'
    | 'accent-filled'
    | 'accent-transparent'
    | 'neutral-tinted'
    | 'neutral-base'
    | 'neutral-transparent'
    | 'critical-tinted'
    | 'critical-transparent'
    | 'inherit-filled'
    | 'inherit-tinted';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  text?: string;
  startIcon?: string;
  endIcon?: string;
  type?: 'button' | 'submit' | 'reset';
  disabled?: boolean;
  loading?: boolean;
  width?: string;
  accessibleLabel?: string;
  /**
   * The named slot to land in.
   *
   * Needed because a wrapper around a slotted button is not neutral: the
   * element places an `nldd-button-group` around whatever lands in its
   * `actions` slot, and a `<div>` in between becomes that group's single item.
   * The buttons then line up against the left edge of a centred dialog rather
   * than under its heading.
   */
  slot?: string;
  children?: ReactNode;
  className?: string;
}

/**
 * `nldd-button` with a React-shaped onClick.
 *
 * Note the label goes in the `text` attribute, not in children. Children land
 * in the `text` slot, which the element only uses when `text` is unset — pass
 * children only for a label with inline markup.
 */
export function NlddButton({
  onClick,
  variant = 'primary',
  size = 'md',
  text,
  startIcon,
  endIcon,
  type = 'button',
  disabled,
  loading,
  width,
  accessibleLabel,
  slot,
  children,
  className,
}: NlddButtonProps) {
  const ref = useRef<HTMLElement>(null);
  const handler = useCallback(() => onClick?.(), [onClick]);
  useNlddEvent(ref, 'click', onClick ? handler : undefined);

  return (
    <nldd-button
      ref={ref}
      variant={variant}
      size={size}
      type={type}
      className={className}
      {...(text ? { text } : {})}
      {...(startIcon ? { 'start-icon': startIcon } : {})}
      {...(endIcon ? { 'end-icon': endIcon } : {})}
      {...(disabled ? { disabled: true } : {})}
      {...(loading ? { loading: true } : {})}
      {...(width ? { width } : {})}
      {...(accessibleLabel ? { 'accessible-label': accessibleLabel } : {})}
      {...(slot ? { slot } : {})}
    >
      {children}
    </nldd-button>
  );
}

interface NlddActionTextProps {
  text: string;
  onClick: () => void;
  /** `xs` for small print; omit to inherit the surrounding size. */
  size?: 'xs' | 'sm' | 'md';
  className?: string;
}

/**
 * Text that reads as a link but performs an in-page action: opening a panel,
 * expanding a section, switching a view. There is no URL behind it.
 *
 * A `<button>`, not `nldd-link`: a link without `href` emits an `<a>` with no
 * href attribute, and that is neither focusable nor keyboard-operable, so it
 * looks operable while it is not. A button is what this is. `plain-button`
 * takes the control chrome off so it still reads as text, and the underline on
 * hover and focus is what says it does something.
 */
export function NlddActionText({ text, onClick, size, className }: NlddActionTextProps) {
  return (
    <button
      type="button"
      className={['plain-button', 'link-hover-underline', className].filter(Boolean).join(' ')}
      onClick={onClick}
    >
      <nldd-text {...(size ? { size } : {})} color="accent">
        {text}
      </nldd-text>
    </button>
  );
}
