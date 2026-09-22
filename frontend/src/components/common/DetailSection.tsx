import type { ReactNode } from 'react';

interface DetailSectionProps {
  title: string;
  icon?: ReactNode;
  count?: number;
  action?: ReactNode;
  separated?: boolean;
  children: ReactNode;
}

/**
 * A titled block inside a detail view.
 *
 * The heading is a small, bold, secondary `nldd-text` rather than an
 * `nldd-title`: these sit inside a modal that already has its own heading, and
 * a second heading level here would make the document outline claim more
 * structure than there is.
 */
export function DetailSection({
  title,
  icon,
  count,
  action,
  separated = false,
  children,
}: DetailSectionProps) {
  return (
    <nldd-container gap="8">
      {separated && <nldd-divider />}
      <nldd-container layout="row" gap="8" vertical-alignment="center">
        <nldd-container layout="row" gap="6" vertical-alignment="center">
          {icon}
          <nldd-text size="xs" weight="bold" color="secondary">
            {count != null ? `${title} (${count})` : title}
          </nldd-text>
        </nldd-container>
        {action && (
          <nldd-container width="fit-content" className="shrink-0" horizontal-alignment="right">
            {action}
          </nldd-container>
        )}
      </nldd-container>
      {children}
    </nldd-container>
  );
}
