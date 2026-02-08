import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('renders title', () => {
    render(<EmptyState title="Geen resultaten" />);
    expect(screen.getByText('Geen resultaten')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(
      <EmptyState
        title="Leeg"
        description="Er zijn nog geen items aangemaakt."
      />,
    );
    expect(screen.getByText('Er zijn nog geen items aangemaakt.')).toBeInTheDocument();
  });

  it('does not render description when not provided', () => {
    const { container } = render(<EmptyState title="Leeg" />);
    expect(container.querySelectorAll('p').length).toBe(0);
  });

  it('renders action when provided', () => {
    render(
      <EmptyState
        title="Leeg"
        action={<button>Nieuw item</button>}
      />,
    );
    expect(screen.getByText('Nieuw item')).toBeInTheDocument();
  });

  it('renders custom icon when provided', () => {
    render(
      <EmptyState
        title="Leeg"
        icon={<span data-testid="custom-icon">!</span>}
      />,
    );
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });
});
