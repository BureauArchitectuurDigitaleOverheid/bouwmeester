import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { LoadingSpinner } from './LoadingSpinner';

/**
 * These assert the contract (an activity indicator at the requested scale),
 * not the markup: asserting on internals says nothing about whether a spinner
 * is actually shown.
 *
 * jsdom does not upgrade custom elements, so nldd-activity-indicator stays an
 * inert tag here. That is enough to check we render the right element with the
 * right attributes; that it spins is the design system's own test.
 */
describe('LoadingSpinner', () => {
  it('renders an activity indicator', () => {
    const { container } = render(<LoadingSpinner />);
    expect(container.querySelector('nldd-activity-indicator')).toBeInTheDocument();
  });

  it('renders medium size by default', () => {
    const { container } = render(<LoadingSpinner />);
    expect(container.querySelector('nldd-activity-indicator')).toHaveAttribute('size', '32');
  });

  it('renders small size', () => {
    const { container } = render(<LoadingSpinner size="sm" />);
    expect(container.querySelector('nldd-activity-indicator')).toHaveAttribute('size', '16');
  });

  it('renders large size', () => {
    const { container } = render(<LoadingSpinner size="lg" />);
    expect(container.querySelector('nldd-activity-indicator')).toHaveAttribute('size', '48');
  });

  it('applies the requested padding', () => {
    const { container } = render(<LoadingSpinner padding="16" />);
    expect(container.querySelector('nldd-container')).toHaveAttribute('padding-block', '16');
  });
});
