type ContainerPadding = NonNullable<React.ComponentProps<'nldd-container'>['padding-block']>;

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  /** Vertical padding around the centered indicator, as an nldd-container
   *  spacer-scale step (e.g. '32'). Replaces the old Tailwind `py-N`
   *  className prop, which no longer compiles to real CSS. */
  padding?: ContainerPadding;
}

/** nldd-activity-indicator sizes in the design system's spacer-aligned steps. */
const SIZES = {
  sm: '16',
  md: '32',
  lg: '48',
} as const;

export function LoadingSpinner({ size = 'md', padding }: LoadingSpinnerProps) {
  return (
    <nldd-container
      width="full"
      horizontal-alignment="center"
      vertical-alignment="center"
      {...(padding ? { 'padding-block': padding } : {})}
    >
      <nldd-activity-indicator size={SIZES[size]} />
    </nldd-container>
  );
}
