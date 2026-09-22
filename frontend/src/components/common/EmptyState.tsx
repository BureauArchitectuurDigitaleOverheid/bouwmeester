import { Children, Fragment, cloneElement, isValidElement, type ReactNode } from 'react';

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
 *
 * Each action gets `slot="actions"` put on it here rather than sharing one
 * wrapper. That slot is not cosmetic: the element derives its alignment from
 * where content lands, and reads anything in the default slot as a task, which
 * it aligns left. A wrapping `<div slot="actions">` still counted as one item
 * for the `nldd-button-group` inside, so the buttons sat against the left edge
 * of a centred dialog instead of under its heading.
 */

/** Flattens fragments and arrays, which `Children.toArray` leaves intact. */
function flatten(node: ReactNode): ReactNode[] {
  return Children.toArray(node).flatMap((child) =>
    isValidElement(child) && child.type === Fragment
      ? flatten((child.props as { children?: ReactNode }).children)
      : [child],
  );
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  const actions = flatten(action).map((child, i) =>
    isValidElement(child)
      ? cloneElement(child as React.ReactElement<{ slot?: string }>, {
          key: i,
          slot: 'actions',
        })
      : child,
  );

  return (
    <nldd-inline-dialog
      icon={typeof icon === 'string' ? icon : 'question-mark-circle'}
      text={title}
      {...(description ? { 'supporting-text': description } : {})}
    >
      {actions}
    </nldd-inline-dialog>
  );
}
