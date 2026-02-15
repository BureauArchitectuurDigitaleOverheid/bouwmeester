import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-primary-900 text-white hover:bg-primary-800 focus-visible:ring-primary-500 shadow-sm',
  secondary:
    'bg-white text-primary-900 ring-1 ring-inset ring-border hover:bg-gray-50 focus-visible:ring-primary-500 shadow-sm',
  danger:
    'bg-red-600 text-white hover:bg-red-500 focus-visible:ring-red-500 shadow-sm',
  ghost:
    'text-text-secondary hover:bg-gray-100 hover:text-text focus-visible:ring-primary-500',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-xs rounded-lg',
  md: 'px-3.5 py-2 text-sm rounded-xl',
  lg: 'px-4 py-2.5 text-sm rounded-xl',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
  loading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={twMerge(
        clsx(
          'inline-flex items-center justify-center gap-2 font-medium transition-all duration-150',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          variantClasses[variant],
          sizeClasses[size],
          className,
        ),
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <svg
          className="h-4 w-4 animate-spin"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      ) : icon ? (
        <span className="h-4 w-4 shrink-0">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}
