import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function AllProviders({ children }: { children: ReactNode }) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  return render(ui, { wrapper: AllProviders, ...options });
}

export { render };

/**
 * TESTING NLDD COMPONENTS IN VITEST — read this before writing an assertion.
 *
 * jsdom registers the nldd-* elements and even builds their shadow roots, but
 * Lit renders nothing into them (the shadow root's content stays `<!---->`),
 * because its render path needs browser APIs jsdom does not implement. Verified
 * directly, not assumed.
 *
 * The consequences, which are permanent for this test setup:
 *
 *  - `getByRole('button', ...)` never finds an `nldd-button`. There is no inner
 *    `<button>` in jsdom, so there is no role and no accessible name.
 *  - `getByText('Opslaan')` never finds a label passed as `text="Opslaan"`,
 *    because it is an attribute, not a text node. Use `getByNlddText`.
 *  - `userEvent.click(...)` on an nldd host does not run the component's own
 *    click handling. Our wrappers listen on the host, so dispatching a `click`
 *    on the host does work — that is what `clickNldd` below does.
 *
 * So a vitest test can assert WHAT WE RENDER (which element, which attributes,
 * which handlers fire), and it cannot assert what the design system renders.
 * Anything that depends on the real thing — roles, focus order, keyboard
 * behaviour, visibility — belongs in the Playwright suite under `e2e/`, which
 * runs a real browser. Do not weaken a test to make it pass here; move it.
 */

/**
 * Find an nldd element whose text lives in an attribute rather than in a text
 * node.
 *
 * Several design system components take their label as `text` /
 * `supporting-text` and render it inside their shadow root, which jsdom does not
 * build. `getByText` therefore finds nothing even though the label is right
 * there on the element. Use this instead:
 *
 *   expect(getByNlddText('Geen resultaten')).toBeInTheDocument();
 */
export function getByNlddText(text: string, container: HTMLElement = document.body) {
  const match = Array.from(container.querySelectorAll('*')).find(
    (el) =>
      el.tagName.toLowerCase().startsWith('nldd-') &&
      (el.getAttribute('text') === text || el.getAttribute('supporting-text') === text),
  );
  if (!match) {
    throw new Error(
      `No nldd-* element with text or supporting-text "${text}". ` +
        `Present: ${Array.from(container.querySelectorAll('[text]'))
          .map((el) => `${el.tagName.toLowerCase()}[text="${el.getAttribute('text')}"]`)
          .join(', ') || '(none)'}`,
    );
  }
  return match as HTMLElement;
}

/**
 * Click an nldd element the way our wrappers listen for it.
 *
 * `userEvent.click` aims at the inner control, which does not exist in jsdom.
 * Our wrappers (NlddButton, NlddIconButton, NlddListItemLink) bind their handler
 * on the host, so dispatching there is what actually exercises them.
 *
 *   clickNldd(getByNlddLabel('Opslaan'));
 *
 * Wrapped in `act` because this is a raw MouseEvent, outside the auto-act that
 * Testing Library puts around its own `userEvent` and `fireEvent` calls. Without
 * it, state updates the handler triggers land after the assertion and React logs
 * "not wrapped in act(...)".
 */
export function clickNldd(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
}

/**
 * Find an nldd element by the label it was given, whichever attribute carries
 * it (`text`, `accessible-label`, `supporting-text`).
 *
 * The closest stand-in for `getByRole(..., { name })` that works here. It is a
 * weaker check — it reads what we passed in, not what a user would hear — so
 * prefer a Playwright test wherever the accessible name is the point.
 */
export function getByNlddLabel(label: string, container: HTMLElement = document.body) {
  const match = Array.from(container.querySelectorAll('*')).find(
    (el) =>
      el.tagName.toLowerCase().startsWith('nldd-') &&
      ['text', 'accessible-label', 'supporting-text'].some(
        (attr) => el.getAttribute(attr) === label,
      ),
  );
  if (!match) throw new Error(`No nldd-* element labelled "${label}"`);
  return match as HTMLElement;
}
