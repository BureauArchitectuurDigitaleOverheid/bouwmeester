import type { ReactNode } from 'react';

interface DetailSectionProps {
  title: string;
  icon?: ReactNode;
  count?: number;
  action?: ReactNode;
  separated?: boolean;
  children: ReactNode;
}

export function DetailSection({ title, icon, count, action, separated = false, children }: DetailSectionProps) {
  return (
    <div className={separated ? 'border-t border-border pt-4' : ''}>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
          {icon}
          {title}
          {count != null && (
            <span className="font-normal normal-case">({count})</span>
          )}
        </h4>
        {action}
      </div>
      {children}
    </div>
  );
}
