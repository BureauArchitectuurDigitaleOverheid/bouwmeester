/**
 * Binding helpers between React and the nldd-* custom elements.
 *
 * Three things React does not do for us, each of which fails silently rather
 * than loudly, which is why they live in one place instead of at every call site:
 *
 * 1. Custom events are not React events. React's synthetic system binds a fixed
 *    set of DOM events through a delegated listener on the root. Events the
 *    design system dispatches with `bubbles: false` never reach it —
 *    `nldd-sheet` dispatches `close` that way (verified in the package source:
 *    `dispatchEvent(new CustomEvent('close', { bubbles: false, composed: true }))`,
 *    while `open` uses `bubbles: true`). An `onClose` JSX prop therefore never
 *    fires. Always `addEventListener` on the element itself.
 *
 * 2. Values arrive in `event.detail`, not on `event.target.value`. Read
 *    defensively: the field components carry a native input underneath, but the
 *    composed ones (combo-box, token-field) do not.
 *
 * 3. Booleans must be `true | undefined`, never `false`. React writes
 *    `expanded={false}` as the attribute `expanded="false"`, and the element
 *    reads mere presence as true — so `false` turns the thing ON. Use `orUndef`.
 */
import { useEffect, useRef, type RefObject } from 'react';

/** An element that exposes the imperative overlay API (sheet, popover, modal). */
export interface NlddOverlayElement extends HTMLElement {
  show?: () => void;
  hide?: () => void;
}

/** A field element that mirrors its value as a property. */
export interface NlddValueElement extends HTMLElement {
  value?: string;
}

/**
 * React renders `false` as the string attribute "false", which a custom element
 * reads as present-and-true. Pass booleans through here.
 *
 *   <nldd-list-item current={orUndef(isActive)} />
 */
export function orUndef(value: boolean | undefined): true | undefined {
  return value ? true : undefined;
}

/** Pull a value out of an nldd event, falling back to the native input under it. */
export function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  if (detail && typeof detail === 'object' && 'value' in detail) {
    const v = detail.value;
    if (typeof v === 'string') return v;
    if (v != null) return String(v);
  }
  const target = event.target as { value?: unknown } | null;
  return typeof target?.value === 'string' ? target.value : '';
}

/**
 * Subscribe to an event on a custom element. Listens on the element itself, so
 * it works for non-bubbling events too.
 *
 * The handler is kept in a ref, so passing an inline arrow does not tear the
 * listener down and rebuild it on every render.
 */
export function useNlddEvent<T extends HTMLElement = HTMLElement>(
  ref: RefObject<T | null>,
  type: string,
  handler: ((event: Event) => void) | undefined,
): void {
  const saved = useRef(handler);
  saved.current = handler;

  useEffect(() => {
    const el = ref.current;
    if (!el || !handler) return;
    const listener = (event: Event) => saved.current?.(event);
    el.addEventListener(type, listener);
    return () => el.removeEventListener(type, listener);
    // `handler` is read through the ref; only its presence matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref, type, handler === undefined]);
}

/**
 * Keep a controlled field's DOM property in step with React state.
 *
 * Custom element values live on the property, not the attribute, and writing it
 * unconditionally on every render would reset the caret mid-word. Only write
 * when the two have actually diverged (an external reset, a refetch).
 */
export function useNlddValue<T extends NlddValueElement>(
  ref: RefObject<T | null>,
  value: string | undefined,
): void {
  useEffect(() => {
    const el = ref.current;
    if (el && value !== undefined && el.value !== value) {
      el.value = value;
    }
  }, [ref, value]);
}

/**
 * Drive a sheet, popover or modal from React state.
 *
 * Mounting and unmounting the element would skip its enter/exit animation and
 * throw away DOM state, so the element stays mounted and we mirror `open` onto
 * its imperative `show()` / `hide()`.
 *
 * The element also closes itself (Escape, click outside, its own dismiss
 * button) and then fires `close`. That has to travel back up to whatever owns
 * `open`, or React would re-open it on the next render. Calling `hide()` from
 * the close handler instead would give a hide -> close -> hide loop, so we only
 * report the close upward when React still believes the overlay is open.
 */
export function useNlddOverlay<T extends NlddOverlayElement>(
  ref: RefObject<T | null>,
  open: boolean,
  onClose?: () => void,
): void {
  const openRef = useRef(open);
  openRef.current = open;
  const savedOnClose = useRef(onClose);
  savedOnClose.current = onClose;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open) el.show?.();
    else el.hide?.();
  }, [ref, open]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const listener = () => {
      // Swallow the echo of our own hide(); only a close the element initiated
      // while React thought it was open needs to travel upward.
      if (openRef.current) savedOnClose.current?.();
    };
    el.addEventListener('close', listener);
    return () => el.removeEventListener('close', listener);
  }, [ref]);
}
