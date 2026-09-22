import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Badge } from './Badge';

/**
 * The twelve variants map onto nldd-tag colors: the ones that carry meaning go
 * to a semantic role (so they stay correct in dark mode and without color
 * vision), the decorative ones to the nearest Rijkshuisstijl color.
 */
describe('Badge', () => {
  const tag = (container: HTMLElement) => container.querySelector('nldd-tag');

  it('passes a plain-string label as the text attribute', () => {
    const { container } = render(<Badge>Actief</Badge>);
    expect(tag(container)).toHaveAttribute('text', 'Actief');
  });

  it('defaults to the neutral role', () => {
    const { container } = render(<Badge>Status</Badge>);
    expect(tag(container)).toHaveAttribute('color', 'neutral');
  });

  it('maps meaningful variants to semantic roles', () => {
    expect(tag(render(<Badge variant="green">Klaar</Badge>).container)).toHaveAttribute(
      'color',
      'success',
    );
    expect(tag(render(<Badge variant="red">Fout</Badge>).container)).toHaveAttribute(
      'color',
      'critical',
    );
    expect(tag(render(<Badge variant="amber">Let op</Badge>).container)).toHaveAttribute(
      'color',
      'warning',
    );
  });

  it('maps decorative variants to Rijkshuisstijl colors', () => {
    expect(tag(render(<Badge variant="purple">Paars</Badge>).container)).toHaveAttribute(
      'color',
      'paars',
    );
    expect(tag(render(<Badge variant="cyan">Cyaan</Badge>).container)).toHaveAttribute(
      'color',
      'hemelblauw',
    );
  });

  it('shows a dot when asked', () => {
    const { container } = render(<Badge dot>Met dot</Badge>);
    expect(tag(container)).toHaveAttribute('icon');
  });

  it('has no dot by default', () => {
    const { container } = render(<Badge>Zonder dot</Badge>);
    expect(tag(container)).not.toHaveAttribute('icon');
  });

  it('applies custom className', () => {
    const { container } = render(<Badge className="mt-2">Custom</Badge>);
    expect(tag(container)).toHaveClass('mt-2');
  });
});
