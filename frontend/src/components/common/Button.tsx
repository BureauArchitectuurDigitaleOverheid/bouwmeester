import {
  Children,
  isValidElement,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from 'react';
import { useNlddEvent } from '@/components/nldd/events';

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

/**
 * This app's variant names, mapped onto `nldd-button`'s.
 *
 * `danger` is `destructive` and `ghost` is `neutral-transparent`: the design
 * system's names for the same intent.
 */
type NlddButtonVariant = NonNullable<React.ComponentProps<'nldd-button'>['variant']>;

const VARIANTS: Record<ButtonVariant, NlddButtonVariant> = {
  primary: 'primary',
  secondary: 'secondary',
  danger: 'destructive',
  ghost: 'neutral-transparent',
};

/** The `sm` breakpoint from utilities.css (`hidden-below-sm`). */
const SM_MIN_WIDTH = 640;

/**
 * Reads a label wrapped in a `<span>`, e.g.
 * `<span className="hidden-below-sm">Nieuwe taak</span>`, and whether it is
 * meant to disappear below `sm`.
 *
 * The wrapper cannot stay a child: `nldd-button` does not display slotted
 * text, so the span rendered as nothing while the button still reserved a
 * text area and the gap before it. That pushed the icon of every such
 * "icon on a phone, label on a desktop" button off centre, and showed the
 * label nowhere. The text therefore goes into the `text` attribute, and the
 * breakpoint is applied here instead of by the class.
 *
 * Only a `<span>` holding plain text counts; other rich children stay in the
 * slot as before.
 */
function findSpanLabel(children: ReactNode): { text: string; hideBelowSm: boolean } | undefined {
  let found: { text: string; hideBelowSm: boolean } | undefined;
  Children.forEach(children, (child) => {
    if (found || !isValidElement(child) || child.type !== 'span') return;
    const props = child.props as { className?: string; children?: ReactNode };
    if (typeof props.children !== 'string') return;
    found = {
      text: props.children,
      hideBelowSm: !!props.className?.split(/\s+/).includes('hidden-below-sm'),
    };
  });
  return found;
}

function useWiderThan(px: number): boolean {
  const query = `(min-width: ${px}px)`;
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia?.(query).matches,
  );
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const onChange = () => setMatches(mq.matches);
    mq.addEventListener('change', onChange);
    setMatches(mq.matches);
    return () => mq.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** An nldd-icon name, or an element to put in the start-icon slot. */
  icon?: ReactNode | string;
  loading?: boolean;
  /**
   * Clips an over-long label with an ellipsis instead of letting it wrap.
   *
   * This has to be the element's own attribute, not a `truncate` class: the
   * label lives in the shadow root, so `overflow` set on the host never
   * reaches it, and the class silently does nothing. The element gates those
   * same three properties on this attribute. Give the button (or an ancestor)
   * a width to clip against, or there is nothing to cut off.
   */
  singleLine?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  singleLine = false,
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
  const spanLabel = typeof children === 'string' ? undefined : findSpanLabel(children);
  const wide = useWiderThan(SM_MIN_WIDTH);
  const showSpanLabel = !!spanLabel && (!spanLabel.hideBelowSm || wide);
  const text = typeof children === 'string' ? children : showSpanLabel ? spanLabel.text : undefined;

  // Below `sm` a responsively hidden label leaves an icon-only button, which
  // still needs a name: a screen reader would otherwise announce nothing.
  const hiddenLabel = spanLabel && !showSpanLabel ? spanLabel.text : undefined;

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
      {...(singleLine ? { 'single-line': true } : {})}
      {...(disabled ? { disabled: true } : {})}
      {...(props as Record<string, unknown>)}
    >
      {/* A non-string icon renders through the start-icon slot instead of the
          `start-icon` attribute. */}
      {icon && typeof icon !== 'string' ? <span slot="start-icon">{icon}</span> : null}
      {text || spanLabel ? null : children}
    </nldd-button>
  );
}
