/**
 * Generates React JSX typings for the nldd-* custom elements.
 *
 * The package ships `dist/types/vue.d.ts` (itself generated from the component
 * classes) but nothing for React, so we derive ours from that file. Both
 * describe the same elements and both reference the element classes for the
 * actual property types, which keeps this honest: a prop renamed upstream shows
 * up as a type error here rather than as a silently ignored attribute.
 *
 * React 19 differences we encode:
 *  - Attributes use the dash spelling only. React passes unknown camelCase
 *    props straight through as attributes, so `accessibleLabel` would land in
 *    the DOM as `accessiblelabel` and be ignored. Vue normalizes, React does not.
 *  - Events are NOT props. React's synthetic system only binds a known set, and
 *    several nldd events (notably `close`) are dispatched with `bubbles: false`,
 *    which React's delegated listeners never see. Use the hooks in
 *    `components/nldd/events.ts` instead; `on*` props are deliberately omitted
 *    so that writing one is a type error rather than a listener that never fires.
 *
 * Run: node scripts/generate-nldd-types.mjs
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

// The package's exports map doesn't expose package.json, so resolve a subpath
// we know is exported and walk back up to the package root from there.
const require = createRequire(import.meta.url);
const pkgRoot = path
  .dirname(require.resolve('@nldd/design-system/button'))
  .replace(/(\/node_modules\/@nldd\/design-system)\/.*$/, '$1');
const vueTypes = readFileSync(path.join(pkgRoot, 'dist/types/vue.d.ts'), 'utf8');

// `import type { NLDDButton } from '@nldd/design-system/button';`
const imports = new Map();
for (const m of vueTypes.matchAll(
  /import type \{ (\w+) \} from '(@nldd\/design-system\/[\w-]+)';/g,
)) {
  imports.set(m[1], m[2]);
}

// `type NLDDButtonProps = { ... };` — non-greedy up to the closing brace at the
// same indentation, which is how the generator formats every block.
//
// The `(?:\n([\s\S]*?))?` is load-bearing: some components have an EMPTY props
// block (`= {\n\t};`). A pattern that demands at least one line in between skips
// those, and the non-greedy match then runs on and swallows the NEXT block —
// which silently cost nldd-form-section its `text` / `supporting-text` props
// until an agent noticed they were missing.
// Matched line by line rather than with one multi-line regex. A non-greedy
// `[\s\S]*?` gets this wrong: several components have an EMPTY props block
// (`= {\n\t};`), the pattern prefers the shorter match there, and the scan then
// runs past the NEXT block and drops it. That silently cost nldd-form-section,
// nldd-button-group, nldd-document-tab-bar and nldd-menu-group all of their
// props until an agent noticed `text` was missing from form-section.
const propBlocks = new Map();
{
  const lines = vueTypes.split('\n');
  let name = null;
  let body = [];
  for (const line of lines) {
    const start = line.match(/^\ttype (\w+)Props = \{$/);
    if (start) {
      name = start[1];
      body = [];
      continue;
    }
    if (name === null) continue;
    if (line === '\t};') {
      propBlocks.set(name, body.join('\n'));
      name = null;
      continue;
    }
    body.push(line);
  }
}

// `'nldd-button': DefineComponent<NLDDButtonProps>;`
const elements = [];
for (const m of vueTypes.matchAll(/'(nldd-[\w-]+)': DefineComponent<(\w+)Props>/g)) {
  elements.push({ tag: m[1], cls: m[2] });
}

if (!elements.length) throw new Error('No nldd-* elements found — did vue.d.ts change shape?');

/** Keep dash-cased attributes and plain lowercase ones; drop camelCase duplicates
 *  (React would pass those through as lowercased attributes) and drop on* event
 *  props (see the header). */
function reactProps(block) {
  const lines = block.split('\n');
  const out = [];
  let doc = [];
  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith('/**')) {
      doc = [t];
      continue;
    }
    const prop = t.match(/^'([\w-]+)'\?: (.+);$/);
    if (!prop) {
      if (t) doc = [];
      continue;
    }
    const [, name, type] = prop;
    const isEvent = /^on[A-Z]/.test(name);
    const isCamel = /[A-Z]/.test(name);
    if (isEvent || isCamel) {
      doc = [];
      continue;
    }
    if (doc.length) out.push(`\t\t\t${doc[0]}`);
    out.push(`\t\t\t'${name}'?: ${type};`);
    doc = [];
  }
  return out;
}

/**
 * Which elements the app actually imports.
 *
 * Typing every element while registering a subset quietly promises that any of them works:
 * an unregistered element renders its children unstyled with no error, so the
 * types would be handing out a trap. The ones that are not imported keep their
 * props (so adding the import is all it takes) but say so in a doc comment.
 */
const registered = new Set(
  [...readFileSync(path.resolve(import.meta.dirname, '../src/components/nldd/register.ts'), 'utf8')
    .matchAll(/@nldd\/design-system\/([a-z-]+)/g)].map((m) => `nldd-${m[1]}`),
);

const body = elements
  .sort((a, b) => a.tag.localeCompare(b.tag))
  .map(({ tag, cls }) => {
    const block = propBlocks.get(cls);
    const props = block ? reactProps(block) : [];
    const note = registered.has(tag)
      ? []
      : [
          `\t\t\t/** NOT REGISTERED. Using this renders its children unstyled with no`,
          `\t\t\t *  error. Add \`import '@nldd/design-system/${tag.replace(/^nldd-/, '')}';\` to`,
          `\t\t\t *  components/nldd/register.ts first. Some elements register through a`,
          `\t\t\t *  parent's module (nldd-table-row with nldd-table); register.test.ts lists`,
          `\t\t\t *  those. */`,
        ];
    return [
      ...note,
      `\t\t\t'${tag}': NlddElement & {`,
      ...props.map((l) => `\t${l}`),
      '\t\t\t};',
    ].join('\n');
  })
  .join('\n');

// Import only the classes the emitted body actually references. Elements with
// no props of their own (nldd-divider, nldd-menu-divider, ...) would otherwise
// leave an unused import behind and fail lint.
const importLines = [...new Set(elements.map((e) => e.cls))]
  .filter((c) => imports.has(c) && new RegExp(`\\b${c}\\[`).test(body))
  .sort()
  .map((c) => `import type { ${c} } from '${imports.get(c)}';`);

const out = `// GENERATED by scripts/generate-nldd-types.mjs — do not edit by hand.
// Regenerate after upgrading @nldd/design-system:
//   node scripts/generate-nldd-types.mjs
//
// Derived from the package's own dist/types/vue.d.ts, which is generated from
// the component classes. See the script header for the React-specific rules.
//
// Two things this file deliberately does NOT give you:
//  - camelCase prop spellings. Use the dash spelling ('accessible-label'):
//    React forwards unknown props as attributes verbatim, lowercasing them, so
//    a camelCase prop silently does nothing.
//  - on* event props. Several nldd events are dispatched with bubbles: false
//    (nldd-sheet's 'close' among them) and React's delegated listeners never
//    see those. Use useNlddEvent / NlddOverlay from './events' instead.
import type { DetailedHTMLProps, HTMLAttributes, Ref } from 'react';

${importLines.join('\n')}

/** Base props every custom element accepts: standard HTML attributes, a ref to
 *  the element itself, and \`class\` (React's \`className\` works too). */
type NlddElement = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
\tref?: Ref<HTMLElement>;
\tclass?: string;
\tslot?: string;
};

declare module 'react' {
\tnamespace JSX {
\t\tinterface IntrinsicElements {
${body}
\t\t}
\t}
}

export {};
`;

const target = path.resolve(import.meta.dirname, '../src/components/nldd/nldd-elements.d.ts');
writeFileSync(target, out);
console.log(`Wrote ${elements.length} element declarations to ${path.relative(process.cwd(), target)}`);
