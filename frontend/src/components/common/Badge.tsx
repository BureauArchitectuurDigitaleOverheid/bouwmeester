import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

type BadgeVariant = 'blue' | 'green' | 'purple' | 'amber' | 'cyan' | 'rose' | 'slate' | 'gray' | 'red' | 'orange';

const variantClasses: Record<BadgeVariant, string> = {
  blue: 'bg-blue-50 text-blue-700 ring-blue-600/20',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  purple: 'bg-purple-50 text-purple-700 ring-purple-600/20',
  amber: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  cyan: 'bg-cyan-50 text-cyan-700 ring-cyan-600/20',
  rose: 'bg-rose-50 text-rose-700 ring-rose-600/20',
  slate: 'bg-slate-50 text-slate-700 ring-slate-600/20',
  gray: 'bg-gray-50 text-gray-600 ring-gray-500/20',
  red: 'bg-red-50 text-red-700 ring-red-600/20',
  orange: 'bg-orange-50 text-orange-700 ring-orange-600/20',
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  dot?: boolean;
  className?: string;
}

export function Badge({ children, variant = 'gray', dot = false, className }: BadgeProps) {
  return (
    <span
      className={twMerge(
        clsx(
          'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap',
          variantClasses[variant],
          className,
        ),
      )}
    >
      {dot && (
        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
      )}
      {children}
    </span>
  );
}
