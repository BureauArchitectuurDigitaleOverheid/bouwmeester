import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { ReactNode, HTMLAttributes } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  hoverable?: boolean;
  padding?: boolean;
}

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
    <div
      className={twMerge(
        clsx(
          'group bg-surface rounded-xl border border-border shadow-sm overflow-hidden',
          hoverable && 'hover:shadow-md hover:border-border-hover transition-all duration-200 cursor-pointer',
          className,
        ),
      )}
      {...props}
    >
      {header && (
        <div className="border-b border-border px-5 py-3.5">
          {header}
        </div>
      )}
      <div className={clsx(padding && 'px-3 py-3 sm:px-5 sm:py-4')}>
        {children}
      </div>
      {footer && (
        <div className="border-t border-border px-5 py-3">
          {footer}
        </div>
      )}
    </div>
  );
}
