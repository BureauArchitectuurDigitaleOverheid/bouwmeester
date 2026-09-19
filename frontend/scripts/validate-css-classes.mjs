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
 * Class names reactflow itself defines and reads.
 *
 * There used to be a file-level exclusion here for the graph views, on the
 * reasoning that their classes belong to reactflow. That was wrong, and it hid
 * 112 dead classes across six files: `bg-purple-100` and `h-3.5` on our own
 * markup are our utilities, not reactflow's, and reactflow's stylesheet has
 * nothing to say about them. Only the handful of names reactflow genuinely
 * owns are exempt, by name rather than by file.
 */
const REACTFLOW_OWNED = /^(react-flow|nodrag|nopan|nowheel|selectable|draggable|connectable|dragging|selected|updating|valid|source|target)(__|--|$)/;

const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    // .ts as well as .tsx: the class names that survived longest were not in
    // markup at all but in the lookup tables in src/types/index.ts, which this
    // walk never opened.
    else if (/\.tsx?$/.test(full) && !full.includes('.test.') && !full.endsWith('.d.ts'))
      files.push(full);
  }
})(SRC);

/**
 * The shape of a Tailwind utility.
 *
 * Used for the second pass below, which reads bare string literals rather than
 * attributes. There the check has to be narrow: a lookup table full of Dutch
 * labels is also a bag of strings, and only things that look like utilities
 * should be judged against our stylesheets.
 */
const TAILWIND_SHAPED =
  /^(bg|text|border|ring|shadow|rounded|p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|w|h|min-w|max-w|min-h|max-h|gap|space|flex|grid|col|row|items|justify|self|order|font|leading|tracking|opacity|z|inset|overflow|cursor|transition|duration|ease|animate|hover|focus|active|disabled|group|sm|md|lg|xl|divide|whitespace|break|truncate|object|aspect|uppercase|lowercase|capitalize|underline|italic)([-:]|$)/;

const unbacked = new Map();
for (const file of files) {
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
      if (defined.has(cls) || REACTFLOW_OWNED.test(cls)) continue;
      if (!unbacked.has(cls)) unbacked.set(cls, `${rel}:${line}`);
    }
  }

  // Second pass: class lists that never appear in an attribute.
  //
  // The FCC traffic lights were three invisible dots for exactly this reason.
  // Their color came from a `Record<..., string>` in src/types holding
  // `bg-emerald-500`, reached the span through a variable, and so never met
  // the regex above. Const maps, ternaries and lookup tables are where the
  // longest-lived Tailwind hides, because nothing about them looks like markup.
  // Comments first. `h-4 w-4` inside a doc comment explaining what the old
  // lucide sizing looked like is prose, not markup, and reporting it trains
  // people to ignore this check.
  const code = source
    .replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m0, p1) => p1 + ' '.repeat(m0.length - p1.length));

  for (const m of code.matchAll(/['"`]([a-z][\w:./[\]%-]*(?:\s+[a-z-][\w:./[\]%-]*)+)['"`]/g)) {
    const parts = m[1].split(/\s+/);
    // Mostly utilities, so a sentence of prose is not mistaken for markup.
    if (parts.filter((p) => TAILWIND_SHAPED.test(p)).length < parts.length * 0.7) continue;
    const line = source.slice(0, m.index).split('\n').length;
    for (const cls of parts) {
      if (defined.has(cls) || REACTFLOW_OWNED.test(cls)) continue;
      if (!TAILWIND_SHAPED.test(cls)) continue;
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
