import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmptyState } from './EmptyState';

/**
 * The title and description are attributes on nldd-inline-dialog rather than
 * text nodes, so these read the attributes. jsdom does not upgrade custom
 * elements, so there is no shadow content to query for.
 */
describe('EmptyState', () => {
  const dialog = (container: HTMLElement) => container.querySelector('nldd-inline-dialog');

  it('renders title', () => {
    const { container } = render(<EmptyState title="Geen resultaten" />);
    expect(dialog(container)).toHaveAttribute('text', 'Geen resultaten');
  });

  it('renders description when provided', () => {
    const { container } = render(
      <EmptyState title="Leeg" description="Er zijn nog geen items aangemaakt." />,
    );
    expect(dialog(container)).toHaveAttribute(
      'supporting-text',
      'Er zijn nog geen items aangemaakt.',
    );
  });

  it('omits the description when not provided', () => {
    const { container } = render(<EmptyState title="Leeg" />);
    expect(dialog(container)).not.toHaveAttribute('supporting-text');
  });

  it('renders action in the actions slot', () => {
    render(<EmptyState title="Leeg" action={<button>Nieuw item</button>} />);
    const action = screen.getByText('Nieuw item');
    expect(action).toBeInTheDocument();
    // The element wraps slotted actions in a button group, so they have to be
    // in the named slot rather than loose in the body.
    expect(action.closest('[slot="actions"]')).not.toBeNull();
  });

  it('uses a named icon', () => {
    const { container } = render(<EmptyState title="Leeg" icon="inbox" />);
    expect(dialog(container)).toHaveAttribute('icon', 'inbox');
  });

  it('falls back to a default icon', () => {
    const { container } = render(<EmptyState title="Leeg" />);
    expect(dialog(container)).toHaveAttribute('icon', 'question-mark-circle');
  });
});
