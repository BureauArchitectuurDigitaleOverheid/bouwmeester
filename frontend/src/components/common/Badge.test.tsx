import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Badge } from './Badge';

/**
 * The twelve entity colors map onto nldd-tag colors: the ones that carry meaning go
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

  it('maps meaningful colors to semantic roles', () => {
    expect(tag(render(<Badge color="groen">Klaar</Badge>).container)).toHaveAttribute(
      'color',
      'success',
    );
    expect(tag(render(<Badge color="rood">Fout</Badge>).container)).toHaveAttribute(
      'color',
      'critical',
    );
    expect(tag(render(<Badge color="geel">Let op</Badge>).container)).toHaveAttribute(
      'color',
      'warning',
    );
  });

  it('passes decorative colors through as Rijkshuisstijl colors', () => {
    expect(tag(render(<Badge color="paars">Paars</Badge>).container)).toHaveAttribute(
      'color',
      'paars',
    );
    expect(tag(render(<Badge color="hemelblauw">Hemelblauw</Badge>).container)).toHaveAttribute(
      'color',
      'hemelblauw',
    );
    expect(tag(render(<Badge color="violet">Violet</Badge>).container)).toHaveAttribute(
      'color',
      'violet',
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
