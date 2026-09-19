/**
 * Checks that every design-system CSS variable the app references actually
 * exists in the package.
 *
 * An undefined custom property does not error and does not warn. `color:
 * var(--primitives-color-typo-700)` simply yields nothing, and the element
 * falls back to whatever it inherits, which is usually close enough to the
 * intended color that nobody notices on the page that was being looked at.
 * Written with a fallback (`var(--wrong-name, #333)`) it is worse: the
 * fallback always wins, so the hard-coded value is what ships and the token is
 * decoration.
 *
 * Both forms turn up in ordinary work. `--primitives-border-radius-lg` looks
 * exactly like a real token; the real one is `--primitives-corner-radius-lg`.
 *
 * Only the three public layers are checked. A `--_local` variable belongs to a
 * component and a `--color-*` one is ours.
 *
 * Run: node scripts/validate-nldd-tokens.mjs
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const pkgRoot = path
  .dirname(require.resolve('@nldd/design-system/button'))
  .replace(/(\/node_modules\/@nldd\/design-system)\/.*$/, '$1');

/** Every token the package defines, across all of its stylesheets. */
const defined = new Set();
const cssDir = path.join(pkgRoot, 'dist/css');
for (const file of readdirSync(cssDir)) {
  if (!file.endsWith('.css')) continue;
  const css = readFileSync(path.join(cssDir, file), 'utf8');
  for (const m of css.matchAll(/(--(?:primitives|semantics|components)-[a-z0-9-]+)\s*:/g)) {
    defined.add(m[1]);
  }
}

if (defined.size === 0) {
  console.error('No tokens found in the package — did dist/css move?');
  process.exit(1);
}

const root = path.resolve(import.meta.dirname, '../src');
const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    else if (/\.(tsx?|css)$/.test(entry)) files.push(full);
  }
})(root);

const problems = [];
for (const file of files) {
  const source = readFileSync(file, 'utf8');
  const rel = path.relative(path.resolve(import.meta.dirname, '..'), file);
  for (const m of source.matchAll(/var\(\s*(--(?:primitives|semantics|components)-[a-z0-9-]*)/g)) {
    const name = m[1];
    if (defined.has(name)) continue;
    const line = source.slice(0, m.index).split('\n').length;
    // A name built by interpolation (`--primitives-color-${x}-500`) ends at the
    // template hole and cannot be checked from here.
    if (source.slice(m.index + m[0].length, m.index + m[0].length + 2) === '${') continue;
    problems.push(`${rel}:${line} var(${name}) is not defined by the design system`);
  }
}

if (problems.length) {
  console.error(`\n${problems.length} unknown design-system token(s):\n`);
  for (const p of problems) console.error(`  ${p}`);
  console.error('\nAn undefined custom property renders nothing, silently.\n');
  process.exit(1);
}

console.log(`nldd tokens OK — ${files.length} files, ${defined.size} tokens known.`);
