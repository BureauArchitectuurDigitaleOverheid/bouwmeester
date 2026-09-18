import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
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
