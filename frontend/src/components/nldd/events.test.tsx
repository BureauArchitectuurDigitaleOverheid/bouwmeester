import { describe, it, expect, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import { useRef } from 'react';
import { eventValue, orUndef, useNlddEvent, useNlddOverlay, useNlddValue } from './events';

/**
 * These cover the three places React and the custom elements disagree. They use
 * plain DOM elements rather than real nldd-* ones: jsdom does not run the
 * components (no shadow DOM support worth the name, and no dialog top layer), so
 * what is worth testing here is our own wiring, not theirs.
 */

describe('orUndef', () => {
  it('maps false to undefined so React omits the attribute', () => {
    // React renders `false` as the string "false", which a custom element reads
    // as present-and-true — the opposite of what was meant.
    expect(orUndef(false)).toBeUndefined();
    expect(orUndef(undefined)).toBeUndefined();
    expect(orUndef(true)).toBe(true);
  });
});

describe('eventValue', () => {
  it('prefers event.detail.value', () => {
    const event = new CustomEvent('input', { detail: { value: 'uit detail' } });
    expect(eventValue(event)).toBe('uit detail');
  });

  it('falls back to target.value when there is no detail', () => {
    const input = document.createElement('input');
    input.value = 'uit target';
    const event = new Event('input');
    Object.defineProperty(event, 'target', { value: input });
    expect(eventValue(event)).toBe('uit target');
  });

  it('returns an empty string when neither is present', () => {
    expect(eventValue(new Event('input'))).toBe('');
  });

  it('stringifies a non-string detail value', () => {
    const event = new CustomEvent('change', { detail: { value: 42 } });
    expect(eventValue(event)).toBe('42');
  });
});

describe('useNlddEvent', () => {
  it('receives a non-bubbling event, which a React prop would miss', () => {
    const onClose = vi.fn();
    let el: HTMLElement | null = null;

    function Harness() {
      const ref = useRef<HTMLDivElement>(null);
      useNlddEvent(ref, 'close', onClose);
      return (
        <div
          ref={(node) => {
            ref.current = node;
            el = node;
          }}
        />
      );
    }

    render(<Harness />);
    act(() => {
      el?.dispatchEvent(new CustomEvent('close', { bubbles: false }));
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps the listener across renders with an inline handler', () => {
    const calls: string[] = [];
    let el: HTMLElement | null = null;

    function Harness({ tag }: { tag: string }) {
      const ref = useRef<HTMLDivElement>(null);
      useNlddEvent(ref, 'ping', () => calls.push(tag));
      return (
        <div
          ref={(node) => {
            ref.current = node;
            el = node;
          }}
        />
      );
    }

    const { rerender } = render(<Harness tag="first" />);
    act(() => void el?.dispatchEvent(new CustomEvent('ping')));
    rerender(<Harness tag="second" />);
    act(() => void el?.dispatchEvent(new CustomEvent('ping')));

    // The second call uses the latest closure, not a stale one.
    expect(calls).toEqual(['first', 'second']);
  });
});

describe('useNlddValue', () => {
  it('writes the property only when it differs', () => {
    const el = document.createElement('input');
    const writes: string[] = [];
    let raw = '';
    Object.defineProperty(el, 'value', {
      get: () => raw,
      set: (v: string) => {
        raw = v;
        writes.push(v);
      },
    });

    function Harness({ value }: { value: string }) {
      const ref = useRef(el);
      useNlddValue(ref, value);
      return null;
    }

    const { rerender } = render(<Harness value="a" />);
    rerender(<Harness value="a" />);
    rerender(<Harness value="b" />);

    // Re-rendering with an unchanged value must not touch the property, or the
    // caret jumps to the end mid-word.
    expect(writes).toEqual(['a', 'b']);
  });
});

describe('useNlddOverlay', () => {
  function makeOverlay() {
    const el = document.createElement('div') as unknown as HTMLElement & {
      show: () => void;
      hide: () => void;
      calls: string[];
    };
    el.calls = [];
    el.show = () => el.calls.push('show');
    el.hide = () => el.calls.push('hide');
    return el;
  }

  it('mirrors open state onto show/hide instead of unmounting', () => {
    const el = makeOverlay();

    function Harness({ open }: { open: boolean }) {
      const ref = useRef(el);
      useNlddOverlay(ref, open);
      return null;
    }

    const { rerender } = render(<Harness open={false} />);
    rerender(<Harness open />);
    rerender(<Harness open={false} />);

    expect(el.calls).toEqual(['hide', 'show', 'hide']);
  });

  it('reports a self-initiated close upward', () => {
    const el = makeOverlay();
    const onClose = vi.fn();

    function Harness({ open }: { open: boolean }) {
      const ref = useRef(el);
      useNlddOverlay(ref, open, onClose);
      return null;
    }

    render(<Harness open />);
    act(() => void el.dispatchEvent(new CustomEvent('close', { bubbles: false })));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('swallows the close that follows our own hide()', () => {
    const el = makeOverlay();
    const onClose = vi.fn();

    function Harness({ open }: { open: boolean }) {
      const ref = useRef(el);
      useNlddOverlay(ref, open, onClose);
      return null;
    }

    const { rerender } = render(<Harness open />);
    rerender(<Harness open={false} />);
    // The element echoes a close after being hidden. Passing that upward would
    // give hide -> close -> hide.
    act(() => void el.dispatchEvent(new CustomEvent('close', { bubbles: false })));

    expect(onClose).not.toHaveBeenCalled();
  });
});
