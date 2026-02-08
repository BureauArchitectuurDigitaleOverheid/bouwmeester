import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from './Badge';

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>Actief</Badge>);
    expect(screen.getByText('Actief')).toBeInTheDocument();
  });

  it('renders with default gray variant', () => {
    render(<Badge>Status</Badge>);
    const badge = screen.getByText('Status');
    expect(badge.className).toContain('bg-gray-50');
  });

  it('renders with specified variant', () => {
    render(<Badge variant="green">Klaar</Badge>);
    const badge = screen.getByText('Klaar');
    expect(badge.className).toContain('bg-emerald-50');
  });

  it('shows dot when dot prop is true', () => {
    const { container } = render(<Badge dot>Met dot</Badge>);
    const dots = container.querySelectorAll('.rounded-full.bg-current');
    expect(dots.length).toBe(1);
  });

  it('does not show dot by default', () => {
    const { container } = render(<Badge>Zonder dot</Badge>);
    const dots = container.querySelectorAll('.rounded-full.bg-current');
    expect(dots.length).toBe(0);
  });

  it('applies custom className', () => {
    render(<Badge className="mt-2">Custom</Badge>);
    const badge = screen.getByText('Custom');
    expect(badge.className).toContain('mt-2');
  });
});
