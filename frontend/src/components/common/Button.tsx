import {
  Children,
  isValidElement,
  useCallback,
  useRef,
  type ButtonHTMLAttributes,
  type ReactNode,
} from 'react';
import { useNlddEvent } from '@/components/nldd/events';

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

/**
 * `nldd-button` behind the previous API.
 *
 * `danger` maps to `destructive` and `ghost` to `neutral-transparent`, which are
 * the design system's names for the same intent.
 */
type NlddButtonVariant = NonNullable<React.ComponentProps<'nldd-button'>['variant']>;

const VARIANTS: Record<ButtonVariant, NlddButtonVariant> = {
  primary: 'primary',
  secondary: 'secondary',
  danger: 'destructive',
  ghost: 'neutral-transparent',
};

/**
 * Reads the text out of a child that is hidden below a breakpoint, e.g.
 * `<span className="hidden-below-sm">Nieuwe taak</span>` (utilities.css:
 * `display: none` below `sm`, `inline` from `sm` up). Returns undefined when
 * there is no such child, so a button with a visible label is untouched.
 */
function findResponsivelyHiddenLabel(children: ReactNode): string | undefined {
  let found: string | undefined;
  Children.forEach(children, (child) => {
    if (found || !isValidElement(child)) return;
    const props = child.props as { className?: string; children?: ReactNode };
    if (!props.className?.split(/\s+/).includes('hidden-below-sm')) return;
    if (typeof props.children === 'string') found = props.children;
  });
  return found;
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** An nldd-icon name, or a node for callers not yet converted. */
  icon?: ReactNode | string;
  loading?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  children,
  className,
  disabled,
  onClick,
  type = 'button',
  ...props
}: ButtonProps) {
  const ref = useRef<HTMLElement>(null);

  const handleClick = useCallback(
    (event: Event) => {
      onClick?.(event as unknown as React.MouseEvent<HTMLButtonElement>);
    },
    [onClick],
  );
  useNlddEvent(ref, 'click', onClick ? handleClick : undefined);

  // The label goes in the `text` attribute; children land in the text slot,
  // which the element only reads when `text` is unset. Plain strings take the
  // attribute so the button can measure and truncate them itself.
  const text = typeof children === 'string' ? children : undefined;

  // A label hidden below a breakpoint (`<span className="hidden-below-sm">`)
  // leaves an icon-only button with NO accessible name on a phone: a screen
  // reader announces nothing at all. Pull that text out and pass it as the
  // accessible name, so the button stays announceable at every width.
  const hiddenLabel = !text ? findResponsivelyHiddenLabel(children) : undefined;

  return (
    <nldd-button
      ref={ref}
      variant={VARIANTS[variant]}
      size={size}
      type={type}
      className={className}
      {...(text ? { text } : {})}
      {...(hiddenLabel ? { 'accessible-label': hiddenLabel } : {})}
      {...(typeof icon === 'string' ? { 'start-icon': icon } : {})}
      {...(loading ? { loading: true } : {})}
      {...(disabled ? { disabled: true } : {})}
      {...(props as Record<string, unknown>)}
    >
      {/* A non-string icon is a leftover lucide element; it still renders in the
          start-icon slot until the call site is converted. */}
      {icon && typeof icon !== 'string' ? <span slot="start-icon">{icon}</span> : null}
      {text ? null : children}
    </nldd-button>
  );
}
