/**
 * Checks the nldd-* markup in our .tsx against the real component API.
 *
 * The generated JSX types already catch a wrong attribute NAME. They do not
 * catch three other things that fail silently in the browser:
 *
 *   - a slot the parent component does not have (the content simply vanishes)
 *   - an icon name outside the closed set (renders nothing)
 *   - an element that is used but never imported in register.ts (renders its
 *     children unstyled, no error anywhere)
 *
 * Each of those cost us real bugs this migration. The design system validates
 * its own documentation the same way, against the same manifest.
 *
 * Run: node scripts/validate-nldd-markup.mjs
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const pkgRoot = path
  .dirname(require.resolve('@nldd/design-system/button'))
  .replace(/(\/node_modules\/@nldd\/design-system)\/.*$/, '$1');

const manifest = JSON.parse(readFileSync(path.join(pkgRoot, 'custom-elements.json'), 'utf8'));

/** tag -> { slots:Set, attrs:Set } from the manifest. */
const api = new Map();
for (const mod of manifest.modules ?? []) {
  for (const decl of mod.declarations ?? []) {
    if (!decl.tagName) continue;
    api.set(decl.tagName, {
      slots: new Set((decl.slots ?? []).map((s) => s.name).filter(Boolean)),
      hasDefaultSlot: (decl.slots ?? []).some((s) => !s.name),
      attrs: new Set((decl.attributes ?? []).map((a) => a.name)),
    });
  }
}

/**
 * Every valid icon name: the registry plus its aliases.
 *
 * Not from the manifest — it types `name` as a plain `string`, so the closed set
 * is invisible there. The registry module is the runtime source of truth and is
 * itself generated, so it cannot drift from what actually renders.
 */
const iconNames = new Set();
{
  const iconDir = path.join(pkgRoot, 'dist/components/content/icon');
  const registry = readFileSync(path.join(iconDir, 'icon-registry.js'), 'utf8');
  for (const m of registry.matchAll(/\[\s*'([a-z0-9][a-z0-9-]*)'\s*,/g)) iconNames.add(m[1]);

  const aliases = readFileSync(path.join(iconDir, 'icon-aliases.js'), 'utf8');
  for (const m of aliases.matchAll(/'([a-z0-9][a-z0-9-]*)'\s*:/g)) iconNames.add(m[1]);
}

const SRC = path.resolve(import.meta.dirname, '../src');
const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    else if (full.endsWith('.tsx')) files.push(full);
  }
})(SRC);

const problems = [];

for (const file of files) {
  const source = readFileSync(file, 'utf8');
  const rel = path.relative(SRC, file);

  // Each opening tag with its attribute text, non-greedy up to the closing >.
  for (const m of source.matchAll(/<(nldd-[a-z-]+)((?:[^>"']|"[^"]*"|'[^']*')*)>/g)) {
    const [, tag, attrText] = m;
    const line = source.slice(0, m.index).split('\n').length;
    const spec = api.get(tag);
    if (!spec) {
      problems.push(`${rel}:${line} <${tag}> is not a component in this version`);
      continue;
    }

    // Nothing here; slots are checked against their real parent below.

    // Icon names, where they are written as a literal.
    for (const attr of ['name', 'icon', 'start-icon', 'end-icon']) {
      const im = attrText.match(new RegExp(`\\b${attr}="([a-z0-9-]+)"`));
      if (!im) continue;
      // `name` on a form control is a field name, not an icon.
      if (attr === 'name' && tag !== 'nldd-icon') continue;
      if (iconNames.size && !iconNames.has(im[1])) {
        problems.push(`${rel}:${line} ${tag} ${attr}="${im[1]}" is not a known icon`);
      }
    }
  }

  // A `slot="x"` has to exist on the ELEMENT THAT ENCLOSES IT, not merely
  // somewhere in the system. This is the check that matters: nldd-table has
  // `empty` but no `no-results`, while nldd-list has both, so the same markup
  // is right in one and silently inert in the other. Content in an undeclared
  // slot is never rendered and never warns.
  const stack = [];
  const tagRe = /<(\/?)(nldd-[a-z-]+)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>/g;
  for (const m of source.matchAll(tagRe)) {
    const [, closing, tag, attrText, selfClosing] = m;
    if (closing) {
      stack.pop();
      continue;
    }

    const slotMatch = attrText.match(/\bslot="([a-z-]+)"/);
    if (slotMatch) {
      const parent = stack[stack.length - 1];
      const parentSpec = parent ? api.get(parent) : null;
      if (parentSpec && !parentSpec.slots.has(slotMatch[1])) {
        const line = source.slice(0, m.index).split('\n').length;
        const has = [...parentSpec.slots].join(', ') || 'only a default slot';
        problems.push(
          `${rel}:${line} slot="${slotMatch[1]}" does not exist on <${parent}> (it has: ${has})`,
        );
      }
    }

    if (!selfClosing) stack.push(tag);
  }
}

if (problems.length) {
  console.error(`\n${problems.length} problem(s) in nldd markup:\n`);
  for (const p of problems) console.error('  ' + p);
  console.error('');
  process.exit(1);
}

console.log(
  `nldd markup OK — ${files.length} files, ${api.size} components and ${iconNames.size} icon names known.`,
);
