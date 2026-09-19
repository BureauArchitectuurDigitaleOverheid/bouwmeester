/**
 * Every class name the app renders must have CSS behind it.
 *
 * This exists because of a whole category of silent breakage. While Tailwind is
 * installed its compiler invents a rule for any class it recognises, so
 * `flex`, `px-4` and `group-hover:opacity-100` work without appearing in any
 * stylesheet we own. Take the package out and they keep compiling, keep passing
 * tsc and eslint, and simply stop having an effect: a hover-reveal button that
 * never reveals, a row that no longer sits on one line.
 *
 * 158 of the 176 class names in use were in that state when this was written,
 * including every "leave it as a documented exception" the migration had agreed
 * on. A comment explaining why a class stays does not keep it working.
 *
 * The check is therefore: collect what our own CSS defines, collect what the
 * .tsx files use, and report the difference. While `@import "tailwindcss"` is
 * still in index.css this runs as a warning; once it goes, it fails.
 *
 * Run: node scripts/validate-css-classes.mjs
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(import.meta.dirname, '../src');

/** Class names our own stylesheets define. */
const defined = new Set();
for (const entry of readdirSync(SRC)) {
  if (!entry.endsWith('.css')) continue;
  const css = readFileSync(path.join(SRC, entry), 'utf8');
  // `.name` at the start of a selector, or inside one (`.group:hover .x`).
  for (const m of css.matchAll(/\.([a-zA-Z][\w-]*)/g)) defined.add(m[1]);
}

/** Is Tailwind still compiling classes for us? */
const stillOnTailwind = /^\s*@import\s+["']tailwindcss["']/m.test(
  readFileSync(path.join(SRC, 'index.css'), 'utf8'),
);

/**
 * Files whose classes are somebody else's to define.
 *
 * The graph views hand their class names to reactflow, which ships its own
 * stylesheet; those were excluded from the migration for the same reason.
 */
const NOT_OURS = /(graph\/|LeadGraphView|CommunityEdgeModal|reactflow)/;

const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    else if (full.endsWith('.tsx') && !full.endsWith('.test.tsx')) files.push(full);
  }
})(SRC);

const unbacked = new Map();
for (const file of files) {
  if (NOT_OURS.test(file)) continue;
  const source = readFileSync(file, 'utf8');
  const rel = path.relative(SRC, file);

  for (const m of source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{'([^']*)'\})/g)) {
    const value = m[1] ?? m[2] ?? m[3] ?? '';
    const line = source.slice(0, m.index).split('\n').length;
    // Strip the expressions inside a template literal before splitting. What is
    // left is the literal class names; the `${...}` parts are conditionals whose
    // own strings are checked where they appear as plain quoted values.
    const literal = value.replace(/\$\{[^}]*\}/g, ' ');

    for (const cls of literal.split(/\s+/)) {
      // A class name, not a fragment of JavaScript that survived the split.
      if (!cls || !/^[a-zA-Z][\w:./[\]%-]*$/.test(cls)) continue;
      // A variant (`hover:`, `sm:`, `group-hover:`) needs its own rule; the
      // bare name existing is not enough, so check the whole thing.
      if (defined.has(cls)) continue;
      if (!unbacked.has(cls)) unbacked.set(cls, `${rel}:${line}`);
    }
  }
}

if (unbacked.size === 0) {
  console.log(`CSS classes OK — ${files.length} files, ${defined.size} classes defined.`);
  process.exit(0);
}

const lines = [...unbacked].map(([cls, where]) => `  ${cls}  (${where})`);

if (stillOnTailwind) {
  console.log(
    `CSS classes: ${unbacked.size} still come from Tailwind's compiler.\n` +
      'These break the moment `@import "tailwindcss"` leaves index.css. Each one\n' +
      'needs a component, a rule in utilities.css, or an inline style.\n',
  );
  for (const l of lines.slice(0, 30)) console.log(l);
  if (lines.length > 30) console.log(`  ... and ${lines.length - 30} more`);
  process.exit(0);
}

console.error(`\n${unbacked.size} class name(s) with no CSS behind them:\n`);
for (const l of lines) console.error(l);
console.error('\nThese render nothing. Add a rule to utilities.css or use a component.\n');
process.exit(1);
