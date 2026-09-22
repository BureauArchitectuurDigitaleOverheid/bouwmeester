/**
 * Every class name the app renders must have CSS behind it.
 *
 * A class with no rule behind it is silent: it compiles, passes tsc and
 * eslint, and simply has no effect. A hover-reveal button that never reveals,
 * a row that does not sit on one line. A comment explaining why a class stays
 * does not keep it working, so this check reads rules, not intent.
 *
 * Collect what our own CSS defines, collect what the .tsx files use, report
 * the difference.
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

/**
 * Class names reactflow itself defines and reads.
 *
 * Exempt by name, never by file: a class on our own markup inside a graph view
 * is still ours, and reactflow's stylesheet has nothing to say about it.
 */
const REACTFLOW_OWNED = /^(react-flow|nodrag|nopan|nowheel|selectable|draggable|connectable|dragging|selected|updating|valid|source|target)(__|--|$)/;

const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    // .ts as well as .tsx: class names also live in the lookup tables in
    // src/types/index.ts, never in markup.
    else if (/\.tsx?$/.test(full) && !full.includes('.test.') && !full.endsWith('.d.ts'))
      files.push(full);
  }
})(SRC);

/**
 * The shape of a utility class name.
 *
 * Used by the second pass below, which reads bare string literals rather than
 * attributes. There the check has to be narrow: a lookup table full of Dutch
 * labels is also a bag of strings, and only things that look like utilities
 * should be judged against our stylesheets.
 */
const UTILITY_SHAPED =
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
  // Const maps, ternaries and lookup tables reach markup through a variable,
  // so the regex above never sees them. A `Record<..., string>` of color
  // classes in src/types is the usual shape.
  //
  // Comments are blanked first: `h-4 w-4` inside a doc comment is prose, not
  // markup, and reporting it trains people to ignore this check.
  const code = source
    .replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m0, p1) => p1 + ' '.repeat(m0.length - p1.length));

  for (const m of code.matchAll(/['"`]([a-z][\w:./[\]%-]*(?:\s+[a-z-][\w:./[\]%-]*)+)['"`]/g)) {
    const parts = m[1].split(/\s+/);
    // Mostly utilities, so a sentence of prose is not mistaken for markup.
    if (parts.filter((p) => UTILITY_SHAPED.test(p)).length < parts.length * 0.7) continue;
    const line = source.slice(0, m.index).split('\n').length;
    for (const cls of parts) {
      if (defined.has(cls) || REACTFLOW_OWNED.test(cls)) continue;
      if (!UTILITY_SHAPED.test(cls)) continue;
      if (!unbacked.has(cls)) unbacked.set(cls, `${rel}:${line}`);
    }
  }
}

/**
 * The other direction: CSS nobody uses.
 *
 * A rule in utilities.css that no .tsx mentions is an error, not a warning: a
 * file that opens by saying it is not a utility framework has to be held to it.
 *
 * Only utilities.css is judged. index.css carries element and global rules
 * whose selectors are not class names we look for in markup.
 */
const utilities = readFileSync(path.join(SRC, 'utilities.css'), 'utf8');
const ours = new Set([...utilities.matchAll(/^\.([a-zA-Z][\w-]*)/gm)].map((m) => m[1]));
const allSource = files.map((f) => readFileSync(f, 'utf8')).join('\n');
const orphans = [...ours].filter((cls) => !new RegExp(`\\b${cls}\\b`).test(allSource));

if (unbacked.size === 0 && orphans.length === 0) {
  console.log(
    `CSS classes OK — ${files.length} files, ${defined.size} classes defined, ` +
      `${ours.size} utilities all in use.`,
  );
  process.exit(0);
}

if (orphans.length > 0 && unbacked.size === 0) {
  console.error(`\n${orphans.length} class(es) in utilities.css that nothing uses:\n`);
  for (const cls of orphans.sort()) console.error(`  .${cls}`);
  console.error('\nDelete the rule, or use it. utilities.css is not a utility framework.\n');
  process.exit(1);
}

const lines = [...unbacked].map(([cls, where]) => `  ${cls}  (${where})`);

console.error(`\n${unbacked.size} class name(s) with no CSS behind them:\n`);
for (const l of lines) console.error(l);
console.error('\nThese render nothing. Add a rule to utilities.css or use a component.\n');
process.exit(1);
