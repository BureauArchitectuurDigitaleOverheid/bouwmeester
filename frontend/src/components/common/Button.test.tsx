import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { Button } from './Button';

/**
 * jsdom does not upgrade custom elements, so there is no real <button> in the
 * shadow root to query by role and no click behaviour to drive with
 * userEvent. These therefore assert what this wrapper is responsible for: the
 * right element, the right attributes, and a click listener bound on the host.
 * Whether the element renders an accessible button is the design system's test.
 */
describe('Button', () => {
  const button = (container: HTMLElement) => container.querySelector('nldd-button');

  it('passes a plain-string label as the text attribute', () => {
    const { container } = render(<Button>Opslaan</Button>);
    expect(button(container)).toHaveAttribute('text', 'Opslaan');
  });

  it('keeps rich children in the slot instead of the attribute', () => {
    const { container } = render(
      <Button>
        <strong>Opslaan</strong>
      </Button>,
    );
    expect(button(container)).not.toHaveAttribute('text');
    expect(container.querySelector('strong')).toBeInTheDocument();
  });

  it('calls onClick when the element emits a click', () => {
    const onClick = vi.fn();
    const { container } = render(<Button onClick={onClick}>Klik</Button>);

    // The real click originates inside the element's shadow root; dispatching on
    // the host is the closest jsdom equivalent.
    button(container)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('marks the element disabled', () => {
    const { container } = render(<Button disabled>Uitgeschakeld</Button>);
    expect(button(container)).toHaveAttribute('disabled');
  });

  it('passes the loading state through', () => {
    // The element keeps its width and blocks activation itself, so it does not
    // also need `disabled` — that would drop it out of the tab order.
    const { container } = render(<Button loading>Laden</Button>);
    expect(button(container)).toHaveAttribute('loading');
  });

  it('maps a named icon to start-icon', () => {
    const { container } = render(<Button icon="plus">Met icoon</Button>);
    expect(button(container)).toHaveAttribute('start-icon', 'plus');
  });

  it('maps danger to the destructive variant', () => {
    const { container } = render(<Button variant="danger">Verwijderen</Button>);
    expect(button(container)).toHaveAttribute('variant', 'destructive');
  });

  it('maps ghost to a transparent variant', () => {
    const { container } = render(<Button variant="ghost">Stil</Button>);
    expect(button(container)).toHaveAttribute('variant', 'neutral-transparent');
  });

  it('passes the size through', () => {
    const { container } = render(<Button size="sm">Klein</Button>);
    expect(button(container)).toHaveAttribute('size', 'sm');
  });
});
