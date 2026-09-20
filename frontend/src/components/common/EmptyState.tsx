import type { ReactNode } from 'react';

interface EmptyStateProps {
  /** An nldd-icon name, or an element to render in its place. */
  icon?: ReactNode | string;
  title: string;
  description?: string;
  action?: ReactNode;
}

/**
 * The "nothing here" state, as an `nldd-inline-dialog`.
 *
 * This is also what belongs in the `empty` / `no-results` slots of nldd-list and
 * nldd-table, which is why those slots ship empty: what an empty list should say
 * is the app's to write.
 */
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <nldd-inline-dialog
      icon={typeof icon === 'string' ? icon : 'question-mark-circle'}
      text={title}
      {...(description ? { 'supporting-text': description } : {})}
    >
      {action && <div slot="actions">{action}</div>}
    </nldd-inline-dialog>
  );
}
