import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';

/**
 * Route smoke tests.
 *
 * Every route has to render, register its custom elements, and produce no
 * console errors. This is the net under the NLDD migration: a conversion that
 * breaks a screen usually breaks it loudly (an unregistered element, a crash in
 * render), and that is exactly what this catches.
 *
 * What it does NOT do is drive the interactions. Those flows are better
 * recorded than synthesised, since a recording captures what someone actually
 * does rather than what a test author imagined.
 */

/** Routes inside the authenticated shell, from App.tsx. */
const ROUTES = [
  { path: '/', title: 'Inbox' },
  { path: '/corpus', title: 'Corpus' },
  { path: '/tasks', title: 'Taken' },
  { path: '/people', title: 'Personen' },
  { path: '/organisatie', title: 'Organisatie' },
  { path: '/eenheid-overzicht', title: null }, // title depends on the user's eenheid
  { path: '/search', title: 'Zoeken' },
  { path: '/parlementair', title: 'Kamerstukken' },
  { path: '/opdrachten', title: 'Opdrachten' },
  { path: '/samenwerkingsverbanden', title: 'Samenwerkingsverbanden' },
  { path: '/admin', title: 'Beheer' },
  { path: '/auditlog', title: 'Auditlog' },
  { path: '/docs', title: 'Handleiding' },
  { path: '/instellingen', title: 'Instellingen' },
  { path: '/leads', title: 'Leads' },
];

/**
 * Console noise we accept.
 *
 * Kept deliberately short: every entry here is a class of real error we have
 * chosen to stop seeing, so each one needs a reason.
 */
const IGNORED = [
  /Failed to load resource/, // a 401/404 from the API is the backend's business
  /\[vite\]/, // HMR chatter in dev
  /Download the React DevTools/,
];

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (IGNORED.some((re) => re.test(text))) return;
    errors.push(text);
  });
  page.on('pageerror', (err) => errors.push(`Uncaught: ${err.message}`));
  return errors;
}

test.describe('routes render', () => {
  for (const route of ROUTES) {
    test(`${route.path} renders without console errors`, async ({ page }) => {
      const errors = collectErrors(page);

      await page.goto(route.path);
      // The shell is the first thing to come up; if it never does, the page is
      // broken regardless of what else loaded.
      await expect(page.locator('nldd-app-view')).toBeAttached({ timeout: 15_000 });

      // Let React Query settle so a late render error still lands in this test.
      await page.waitForLoadState('networkidle');

      expect(errors, `console errors on ${route.path}`).toEqual([]);
    });
  }
});

test.describe('shell', () => {
  test('registers its custom elements', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nldd-app-view')).toBeAttached();

    // An element that never upgrades renders its children unstyled and is easy
    // to miss by eye, so assert the upgrade rather than the markup.
    const unupgraded = await page.evaluate(() => {
      const tags = new Set(
        [...document.querySelectorAll('*')]
          .map((el) => el.tagName.toLowerCase())
          .filter((t) => t.startsWith('nldd-')),
      );
      return [...tags].filter((t) => !customElements.get(t));
    });

    expect(unupgraded, 'nldd-* elements used but never registered').toEqual([]);
  });

  test('has a skip link as the first focusable element', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nldd-skip-link')).toBeAttached();

    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName.toLowerCase());
    expect(focused).toBe('nldd-skip-link');
  });

  test('renders the sidebar navigation', async ({ page }) => {
    await page.goto('/');
    const nav = page.locator('nldd-list[type="navigation"]').first();
    await expect(nav).toBeAttached();
    // The rows are links, so they survive a reload and can be opened in a tab.
    await expect(nav.locator('nldd-list-item').first()).toBeAttached();
  });
});

test.describe('layout at width', () => {
  test('desktop shows the sidebar pane', async ({ page }) => {
    test.skip(test.info().project.name !== 'desktop', 'desktop only');
    await page.goto('/');
    await expect(page.locator('[slot="primary-sidebar"]')).toBeVisible();
  });

  test('narrow screens collapse the sidebar out of the layout', async ({ page }) => {
    test.skip(test.info().project.name !== 'mobile', 'mobile only');
    await page.goto('/');
    await expect(page.locator('nldd-app-view')).toBeAttached();

    // Below lg the split view moves the sidebar into its own sheet, so the pane
    // should not be occupying layout width next to the content.
    const sidebarWidth = await page
      .locator('[slot="primary-sidebar"]')
      .evaluate((el) => el.getBoundingClientRect().width)
      .catch(() => 0);
    expect(sidebarWidth).toBeLessThan(200);
  });

  test('has no horizontal scroll', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nldd-app-view')).toBeAttached();
    await page.waitForLoadState('networkidle');

    // WCAG 1.4.10: content reflows without a horizontal scrollbar.
    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );
    expect(overflows, 'page scrolls horizontally').toBe(false);
  });
});

test.describe('modal', () => {
  // This moved out of the unit tests when Modal went to nldd-window: Escape and
  // the backdrop click are the native <dialog>'s own behaviour, and jsdom does
  // not implement showModal, so there is nothing there to press Escape against.
  test('opens and closes on Escape', async ({ page }) => {
    test.skip(test.info().project.name !== 'desktop', 'desktop only');
    await page.goto('/tasks');
    await expect(page.locator('nldd-app-view')).toBeAttached({ timeout: 15_000 });
    await page.waitForLoadState('networkidle');

    const found = await page.evaluate(() => {
      const w = [...document.querySelectorAll('nldd-window')].find(
        (el) => el.getAttribute('accessible-label') === 'Nieuwe taak aanmaken',
      ) as (HTMLElement & { show?: () => void }) | undefined;
      w?.show?.();
      return !!w;
    });
    expect(found, 'the task create window should be mounted').toBe(true);
    await page.waitForTimeout(400);

    const isOpen = () =>
      page.evaluate(() =>
        [...document.querySelectorAll('nldd-window')].some((el) =>
          el.shadowRoot?.querySelector('dialog')?.hasAttribute('open'),
        ),
      );

    expect(await isOpen()).toBe(true);

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    expect(await isOpen(), 'Escape should close the window').toBe(false);
  });
});
