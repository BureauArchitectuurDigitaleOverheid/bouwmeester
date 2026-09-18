import { test, expect } from '@playwright/test';

/**
 * Visual baseline for the migration.
 *
 * Conversions change markup wholesale, so a diff of the rendered page is the
 * only cheap way to see what a change actually did. Take a baseline before
 * converting a domain (`--update-snapshots`), convert, then compare.
 *
 * These are expected to differ deliberately and often. A diff is a prompt to
 * look, not a failure in itself: accept it once the change is what you wanted.
 * That is also why they live in their own file, so `smoke.spec.ts` stays a
 * hard pass/fail signal.
 */

const PAGES = [
  { path: '/', name: 'inbox' },
  { path: '/corpus', name: 'corpus' },
  { path: '/tasks', name: 'tasks' },
  { path: '/organisatie', name: 'organisatie' },
  { path: '/opdrachten', name: 'opdrachten' },
  { path: '/leads', name: 'leads' },
  { path: '/admin', name: 'admin' },
  { path: '/auditlog', name: 'auditlog' },
  { path: '/instellingen', name: 'instellingen' },
];

for (const target of PAGES) {
  test(`${target.name} looks unchanged`, async ({ page }) => {
    await page.goto(target.path);
    await expect(page.locator('nldd-app-view')).toBeAttached({ timeout: 15_000 });
    await page.waitForLoadState('networkidle');

    // Activity indicators and any transition would make every run differ.
    await page.addStyleTag({
      content: `*, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
      }`,
    });

    await expect(page).toHaveScreenshot(`${target.name}.png`, {
      fullPage: true,
      // Text rendering varies by a pixel or two between runs on the same machine.
      maxDiffPixelRatio: 0.01,
    });
  });
}
