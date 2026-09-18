import { defineConfig, devices } from '@playwright/test';

/**
 * Smoke suite for the NLDD migration.
 *
 * It exists to answer one question per release: does every route still render,
 * without console errors, and does it still look like it did before the last
 * conversion? That is deliberately shallow — it is a safety net for a
 * presentation refactor, not a functional test suite.
 *
 * It expects the app on http://localhost:3000 and a backend behind it. Start
 * them with `just up` first; the suite does not manage the stack, because the
 * backend needs a database and migrations that are outside Playwright's remit.
 */
export default defineConfig({
  testDir: './e2e',
  // A migration is a whole-suite affair: failing fast hides how much broke.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',

  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      // The split view collapses the sidebar into a sheet below lg (1008px), so
      // a narrow project is what actually exercises that path.
      name: 'mobile',
      use: { ...devices['Pixel 7'] },
    },
  ],
});
