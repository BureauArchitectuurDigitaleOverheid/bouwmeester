import { useEffect } from 'react';
import { render, act } from '@testing-library/react';
import { describe, it, expect, beforeAll } from 'vitest';
import { ToastProvider, useToast } from './ToastContext';

/**
 * nldd-notification moves itself into a shared region when it connects. When
 * React rendered it, dismissing one of several made React call removeChild on
 * the parent it had rendered it into, which threw NotFoundError and unmounted
 * the app. These tests run the real element.
 */
beforeAll(async () => {
  // The design system's tooltip reads matchMedia at import; jsdom has none.
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  })) as unknown as typeof window.matchMedia;
  await import('@nldd/design-system/notification');
});

const handle: { api: ReturnType<typeof useToast> | null } = { api: null };
function Grab() {
  const toast = useToast();
  useEffect(() => {
    handle.api = toast;
  }, [toast]);
  return null;
}
const api = () => handle.api!;

/** Let the element's queued move into the region run. */
async function settle() {
  await act(async () => {
    await Promise.resolve();
  });
}

const notifications = () => Array.from(document.querySelectorAll('nldd-notification'));

describe('ToastProvider', () => {
  it('dismisses one of several notifications without throwing', async () => {
    const { unmount } = render(
      <ToastProvider>
        <Grab />
      </ToastProvider>,
    );
    await act(async () => {
      api().showSuccess('eerste');
      api().showSuccess('tweede');
    });
    await settle();
    expect(notifications()).toHaveLength(2);

    const first = notifications().find((n) => n.getAttribute('text') === 'eerste')!;
    await act(async () => {
      first.dispatchEvent(new CustomEvent('dismiss', { bubbles: true, composed: true }));
    });
    await settle();

    expect(notifications().map((n) => n.getAttribute('text'))).toEqual(['tweede']);

    unmount();
    expect(notifications()).toHaveLength(0);
  });

  it('runs the action and removes the notification', async () => {
    let undone = false;
    const { unmount } = render(
      <ToastProvider>
        <Grab />
      </ToastProvider>,
    );
    await act(async () => {
      api().showWarning('verwijderd', { label: 'Ongedaan maken', onAction: () => (undone = true) });
    });
    await settle();

    const button = document.querySelector('nldd-notification nldd-button[slot="actions"]')!;
    expect(button.getAttribute('text')).toBe('Ongedaan maken');
    await act(async () => {
      button.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
    });
    await settle();

    expect(undone).toBe(true);
    expect(notifications()).toHaveLength(0);
    unmount();
  });
});
