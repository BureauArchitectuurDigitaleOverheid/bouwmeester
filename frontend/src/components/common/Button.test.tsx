import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from './Button';

describe('Button', () => {
  it('renders children text', () => {
    render(<Button>Opslaan</Button>);
    expect(screen.getByRole('button', { name: 'Opslaan' })).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Klik</Button>);

    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Uitgeschakeld</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when loading', () => {
    render(<Button loading>Laden</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('shows spinner SVG when loading', () => {
    const { container } = render(<Button loading>Laden</Button>);
    expect(container.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    render(<Button icon={<span data-testid="icon">+</span>}>Met icoon</Button>);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('applies danger variant classes', () => {
    render(<Button variant="danger">Verwijderen</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('bg-red-600');
  });

  it('applies size classes', () => {
    render(<Button size="sm">Klein</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('text-xs');
  });
});
