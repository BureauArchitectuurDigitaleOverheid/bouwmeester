type ContainerPadding = NonNullable<React.ComponentProps<'nldd-container'>['padding-block']>;

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  /** Vertical padding around the centered indicator, as an nldd-container
   *  spacer-scale step (e.g. '32'). */
  padding?: ContainerPadding;
  /** Visible text beside the indicator, e.g. "Laden...". */
  text?: string;
}

/** nldd-activity-indicator sizes in the design system's spacer-aligned steps. */
const SIZES = {
  sm: '16',
  md: '32',
  lg: '48',
} as const;

export function LoadingSpinner({ size = 'md', padding, text }: LoadingSpinnerProps) {
  return (
    <nldd-container
      width="full"
      horizontal-alignment="center"
      vertical-alignment="center"
      {...(padding ? { 'padding-block': padding } : {})}
    >
      <nldd-activity-indicator size={SIZES[size]} {...(text ? { text, 'show-text': true } : {})} />
    </nldd-container>
  );
}
