import { clsx } from 'clsx';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/** nldd-activity-indicator sizes in the design system's spacer-aligned steps. */
const SIZES = {
  sm: '16',
  md: '32',
  lg: '48',
} as const;

export function LoadingSpinner({ size = 'md', className }: LoadingSpinnerProps) {
  return (
    <div className={clsx('flex items-center justify-center', className)}>
      <nldd-activity-indicator size={SIZES[size]} />
    </div>
  );
}
