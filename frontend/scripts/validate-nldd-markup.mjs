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
 * The design system validates its own documentation the same way, against the
 * same manifest.
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
/**
 * Elements that take their width from their parent rather than their content.
 * `nldd-container layout="wrap"` has to know how wide it may get before it can
 * decide where to break, and a segmented control is a grid that fills its box.
 */
const MEASURES_PARENT = new Set(['nldd-container', 'nldd-segmented-control']);

/**
 * Elements that size themselves to their content, so a child from the set above
 * finds nothing to measure against.
 */
const SIZES_TO_CONTENT = new Set(['nldd-toolbar-item']);

// Rows that are composed of cells, and the controls that fill whatever width
// they get unless told otherwise.
const ROWS = new Set(['nldd-list-item', 'nldd-table-row', 'nldd-list-item-segment']);
const FILLS_BY_DEFAULT = new Set([
  'nldd-dropdown',
  'nldd-text-field',
  'nldd-combo-box',
  'nldd-search-field',
  'nldd-date-field',
]);

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

/**
 * Whether a non-nldd element (a <div>, a <button>, a React component) is still
 * open at `to`, counting from `from`. The structural checks track nldd-* tags
 * only, so this tells a real parent/child pair from one with something in
 * between that is the actual flex item.
 */
function hasElementBetween(src, from, to) {
  if (from === undefined) return false;
  const text = src.slice(from, to);
  const tag = /<(\/?)([A-Za-z][\w.-]*)/g;
  const open = [];
  let m;
  while ((m = tag.exec(text))) {
    const before = text.slice(Math.max(0, m.index - 1), m.index);
    // A `<` after a word character or `)` is a comparison or a generic, not JSX.
    if (/[\w)\]]/.test(before)) continue;
    let i = tag.lastIndex;
    let depth = 0;
    let quote = null;
    for (; i < text.length; i++) {
      const c = text[i];
      if (quote) {
        if (c === quote && text[i - 1] !== '\\') quote = null;
        continue;
      }
      if (c === '"' || c === "'" || c === '`') quote = c;
      else if (c === '{') depth++;
      else if (c === '}') depth--;
      else if (c === '>' && depth === 0) break;
    }
    if (i >= text.length) break;
    const name = m[2];
    const selfClosing = text[i - 1] === '/';
    tag.lastIndex = i + 1;
    if (name.startsWith('nldd-')) continue;
    if (m[1]) {
      const at = open.lastIndexOf(name);
      if (at !== -1) open.length = at;
    } else if (!selfClosing) {
      open.push(name);
    }
  }
  return open.length > 0;
}

for (const file of files) {
  const source = readFileSync(file, 'utf8');
  const rel = path.relative(SRC, file);

  // Each opening tag with its attribute text, via the brace-counting scanner
  // below. A plain regex cannot do this: it stops at the first `>` it sees,
  // including one inside a JSX expression, and then reads one element's
  // attributes as the previous one's.
  for (const m of scanTags(source)) {
    const [, closingSlash, tag, attrText] = m;
    if (closingSlash) continue;
    const line = source.slice(0, m.index).split('\n').length;
    const spec = api.get(tag);
    if (!spec) {
      problems.push(`${rel}:${line} <${tag}> is not a component in this version`);
      continue;
    }

    // Nothing here; slots are checked against their real parent below.

    // An attribute the element does not have. Unlike a wrong prop in React,
    // a stray attribute on a custom element is not an error: it lands in the
    // DOM and the component never reads it. `hide-above` on an nldd-container
    // is the case that prompted this — it is real on the CELL components, so
    // it looks right, and on a container it silently does nothing.
    //
    // The generated types catch this for a literal attribute, but only where
    // the element is written directly; a wrapper component that spreads props
    // slips past, and so does anything typed loosely.
    for (const am of attrText.matchAll(/(?:^|\s)([a-z][a-z0-9-]*)=/g)) {
      const name = am[1];
      if (spec.attrs.size === 0) break;
      // React/JSX and global HTML attributes are not the component's business.
      if (
        spec.attrs.has(name) ||
        name === 'class' ||
        name === 'slot' ||
        name === 'style' ||
        name === 'id' ||
        name === 'key' ||
        name === 'ref' ||
        name === 'title' ||
        name === 'hidden' ||
        name === 'role' ||
        name.startsWith('data-') ||
        name.startsWith('aria-')
      ) {
        continue;
      }
      problems.push(`${rel}:${line} ${tag} has no attribute "${name}"`);
    }

    // `class` instead of `className`. The generated types allow `class`,
    // because a custom element really does take that attribute, but React does
    // not apply it: it is not in React's known-attribute list for this element,
    // so it lands nowhere and the styling silently does nothing. An agent hit
    // this with `class="hidden sm:flex"`, which meant the element never hid.
    if (/\bclass="/.test(attrText)) {
      problems.push(`${rel}:${line} ${tag} uses class="…"; React needs className`);
    }

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

  // The same names again, but anywhere in the file rather than only on a literal
  // nldd-* tag. Half of this codebase passes icons through React wrappers
  // (<NlddIconButton icon="check-mark">, <NlddButton startIcon={...}>, <Icon name="...">), and those
  // never match the tag scan above: four wrong names once shipped that way, and
  // a wrong name renders nothing at all with no error. A string in a ternary
  // (`icon={on ? 'a' : 'b'}`) is checked too, since that is how every toggle in
  // the app picks its glyph.
  //
  // Only quoted literals are checked. A name held in a variable or a lookup
  // table is out of reach here; the map itself is where that gets read.
  if (iconNames.size) {
    const seen = new Set();
    for (const m of source.matchAll(/(?:\b(?:icon|start-icon|end-icon|startIcon|endIcon)|<Icon\s+name)=(?:"([^"]+)"|\{([^{}]*)\})/g)) {
      const line = source.slice(0, m.index).split('\n').length;
      // Strip comparison operands first: `typeof icon === 'string'` inside the
      // expression is a type test, not an icon name.
      const expr = m[2]?.replace(/[=!]==?\s*'[a-z0-9-]+'/g, '');
      const candidates = m[1] ? [m[1]] : [...expr.matchAll(/'([A-Za-z0-9-]+)'/g)].map((s) => s[1]);
      for (const name of candidates) {
        const key = `${line}:${name}`;
        if (seen.has(key) || iconNames.has(name)) continue;
        seen.add(key);
        problems.push(`${rel}:${line} icon="${name}" is not a known icon`);
      }
    }
  }

  // A `slot="x"` has to exist on the ELEMENT THAT ENCLOSES IT, not merely
  // somewhere in the system. This is the check that matters: nldd-table has
  // `empty` but no `no-results`, while nldd-list has both, so the same markup
  // is right in one and silently inert in the other. Content in an undeclared
  // slot is never rendered and never warns.
  const stack = [];
  // Tracking the parent by regex is only reliable while the open tag contains
  // no nested JSX braces; a `style={{ ... }}` object defeats any single
  // expression. So the stack is abandoned as soon as a tag looks like that, and
  // the remaining slots in that file are skipped rather than blamed on the
  // wrong parent. A missed check beats a false accusation.
  // Braces are counted rather than matched. No regex can balance them at
  // arbitrary depth, and the real markup goes three levels deep
  // (`{...(cond ? { 'supporting-text': x } : {})}`). Each failed attempt at a
  // cleverer pattern left some files unscannable, and an unscannable file
  // silently skips EVERY structural check below — LeadsPage was in that state
  // and was exactly the file whose collapsed toolbar item started all this.
  //
  // Yields the same shape the old regex did: [, closing, tag, attrs].
  function* scanTags(src) {
    const opener = /<(\/?)(nldd-[a-z-]+)/g;
    let m;
    while ((m = opener.exec(src))) {
      let i = opener.lastIndex;
      let depth = 0;
      let quote = null;
      for (; i < src.length; i++) {
        const c = src[i];

        // Comments come FIRST, before the quote check. Their prose is full of
        // apostrophes ("the segment's width", "whose width"), and a quote
        // opened there never closes, so the scan runs past the end of the tag
        // and the next element's attributes get blamed on this one. Checking
        // quotes first meant the comment skip below could never fire.
        if (!quote && c === '/' && src[i + 1] === '/') {
          const nl = src.indexOf('\n', i);
          if (nl === -1) return;
          i = nl;
          continue;
        }
        if (!quote && c === '/' && src[i + 1] === '*') {
          const end = src.indexOf('*/', i + 2);
          if (end === -1) return;
          i = end + 1;
          continue;
        }
        if (quote) {
          if (c === quote && src[i - 1] !== '\\') quote = null;
          continue;
        }
        if (c === '"' || c === "'" || c === '`') quote = c;
        else if (c === '{') depth++;
        else if (c === '}') depth--;
        else if (c === '>' && depth === 0) break;
      }
      if (i >= src.length) return; // unterminated tag: stop rather than guess
      const attrs = src.slice(opener.lastIndex, i);
      const out = [src.slice(m.index, i + 1), m[1], m[2], attrs];
      out.index = m.index;
      yield out;
      opener.lastIndex = i + 1;
    }
  }

  // An open tag the regex cannot consume (a nested `style={{ ... }}` object,
  // say) is skipped entirely, which silently leaves the wrong element on the
  // stack and blames its children's slots on it. Every `<nldd-` in the file is
  // counted first; if the scanner sees fewer, the parent tracking is not
  // trustworthy here and the slot check is skipped for this file. A missed
  // check beats a false accusation.
  /** The open tag's attributes, per stack depth, for the collapse check below. */
  const attrsByDepth = [];
  /** Per open element: its nldd-container children that take 100% width. */
  const fullWidthKids = [];
  /** Per open element: where its opening tag ends in the source. */
  const openIndexByDepth = [];

  const openTagCount = (source.match(/<nldd-[a-z-]+/g) ?? []).length;
  const scannedCount = [...scanTags(source)].filter((m) => !m[1]).length;
  const stackIsReliable = scannedCount === openTagCount;

  for (const m of scanTags(source)) {
    const [, closing, tag, rawAttrs] = m;
    const selfClosing = rawAttrs.trimEnd().endsWith('/');
    const attrText = rawAttrs;
    if (closing) {
      // A container's children are all known once it closes.
      //
      // An nldd-container without a width is 100% wide, and so is one with
      // width="full". In a `wrap` container every such child takes a line of
      // its own: "Aangemaakt" and "5 verbindingen" stacked on two lines with
      // room to spare. In a `row` two of them split the row evenly: half a
      // phone screen for three icon buttons, the other half for the title,
      // which then broke every few words. It happened on five screens.
      //
      // Give the child that should only be as wide as its content
      // `width="fit-content"` with `shrink-0`, and the one that should take
      // the rest `row-fill` (or keep it at 100% as the only one).
      const depth = stack.length - 1;
      const kids = fullWidthKids[depth] ?? [];
      const layout = (attrsByDepth[depth] ?? '').match(/\blayout="([a-z]+)"/)?.[1];
      if (stackIsReliable && stack[depth] === 'nldd-container') {
        if (layout === 'wrap') {
          for (const line of kids) {
            problems.push(
              `${rel}:${line} <nldd-container> at full width inside a wrap: it takes a ` +
                'line of its own. Give it width="fit-content" and shrink-0.',
            );
          }
        } else if (layout === 'row' && kids.length >= 2) {
          problems.push(
            `${rel}:${kids[0]} ${kids.length} full-width <nldd-container>s in one row ` +
              `(lines ${kids.join(', ')}) split it evenly. Size the one that should ` +
              'fit its content with width="fit-content" and shrink-0.',
          );
        }
      }
      fullWidthKids[depth] = [];
      stack.pop();
      continue;
    }

    const slotMatch = stackIsReliable ? attrText.match(/\bslot="([a-z-]+)"/) : null;
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

    // A width-less parent holding a child that measures ITS parent. The two
    // wait on each other and both end at zero: the element renders nothing
    // while keeping its height, so a filter row or a set of pills disappears
    // and leaves a gap in the layout.
    //
    // A container or toolbar-item needs a measure of its own: `min-width`, a
    // fixed `width`, or `max-width`. `width="fit-content"` is NOT one, since
    // that is the "measure my content" mode that starts the deadlock.
    if (stackIsReliable && MEASURES_PARENT.has(tag)) {
      const parent = stack[stack.length - 1];
      if (parent && SIZES_TO_CONTENT.has(parent)) {
        const parentAttrs = attrsByDepth[stack.length - 1] ?? '';
        const hasOwnMeasure =
          /\bmin-width="/.test(parentAttrs) ||
          /\bmax-width="/.test(parentAttrs) ||
          /\bwidth="(?!fit-content")/.test(parentAttrs);
        if (!hasOwnMeasure) {
          const line = source.slice(0, m.index).split('\n').length;
          problems.push(
            `${rel}:${line} <${parent}> holds a <${tag}> but has no width of its own; ` +
              'both collapse to zero. Give the parent a min-width.',
          );
        }
      }
    }

    // `width="fit-content"` on a container that is a flex item, with nothing
    // saying how much room it may take. The mode means "measure my content",
    // and as a flex item that leaves it without a floor: it settles on zero,
    // or on its narrowest word. All three have shipped. A button squeezed into
    // a two-letter block, a heading set one letter per line, and a row of
    // controls hanging over the edge of the popover it belonged in.
    //
    // And it never measures its content at all: the container's layout box
    // is `container-type: inline-size`, which ignores what is inside it, so
    // `fit-content` is 0px. `shrink-0` and `keep-label-width` were accepted
    // here once and turned out to keep it at exactly that 0px (measured,
    // 2026-09-26). What works: `row-fill` (grow into what is left), or an
    // explicit non-zero `min-width`. For a group that should be as wide as its
    // content, use a plain element with the `hug` class instead.
    if (
      stackIsReliable &&
      tag === 'nldd-container' &&
      /\bwidth="fit-content"/.test(attrText)
    ) {
      const rowFill = /\bclassName="[^"]*\brow-fill\b/.test(attrText);
      const floor = /\bmin-width="(?!0(px)?")/.test(attrText);
      // row-fill's `min-width: 0` is outer CSS and beats the attribute, so
      // the two together leave no floor at all. `grow` is row-fill without it.
      if (rowFill && floor) {
        const line = source.slice(0, m.index).split('\n').length;
        problems.push(
          `${rel}:${line} row-fill cancels this container's min-width (its min-width: 0 wins). ` +
            'Use className="grow" to keep the floor.',
        );
      }
      const guarded = rowFill || floor;
      if (!guarded) {
        const line = source.slice(0, m.index).split('\n').length;
        problems.push(
          `${rel}:${line} <nldd-container width="fit-content"> is 0px wide (it never measures ` +
            'its content). Use row-fill, a non-zero min-width, or a plain element with class "hug".',
        );
      }
    }

    // A field control bare in a list or table row. A row is made of cells:
    // text cells share the width that is left, so an element that fills its
    // space by default takes that space from them. An nldd-dropdown without
    // `width` did exactly that in the eenheden beheer: on a phone the name
    // cell next to it was one character wide and "RegelRecht" came out as a
    // column of letters. Put the control in an `nldd-cell`, and give a
    // dropdown a `width`.
    if (stackIsReliable && ROWS.has(stack[stack.length - 1]) && FILLS_BY_DEFAULT.has(tag)) {
      const line = source.slice(0, m.index).split('\n').length;
      problems.push(
        `${rel}:${line} <${tag}> directly in <${stack[stack.length - 1]}>: it fills the row ` +
          'and squeezes the text cells. Put it in an <nldd-cell> (a dropdown with a width).',
      );
    }
    if (
      stackIsReliable &&
      tag === 'nldd-dropdown' &&
      stack[stack.length - 1] === 'nldd-cell' &&
      ROWS.has(stack[stack.length - 2]) &&
      !/\bwidth="/.test(attrText)
    ) {
      const line = source.slice(0, m.index).split('\n').length;
      problems.push(
        `${rel}:${line} <nldd-dropdown> in a row cell without width: it stretches ` +
          'to fill the row. Give it a width.',
      );
    }

    // A container sitting directly inside a card, without padding of its own.
    // `nldd-card` draws the frame and the fill but no inset (measured: zero,
    // with and without `href`), so the text ends up against the border. Three
    // screens shipped that way: the database sections, the environment
    // variables and the Mattermost block.
    //
    // A card holding only a list is fine, and says so by having no container
    // in between: a list row brings its own padding and its background is
    // meant to run edge to edge.
    if (
      stackIsReliable &&
      tag === 'nldd-container' &&
      stack[stack.length - 1] === 'nldd-card' &&
      !/\bpadding/.test(attrText)
    ) {
      // Unless it opens with a divider or a list. Both are meant to run to
      // the card's edge, and an inset there would leave the line floating
      // short of the border it is drawn against.
      const rest = source.slice(m.index + m[0].length, m.index + m[0].length + 200);
      const opensEdgeToEdge = /^\s*\{?\s*<nldd-(divider|list|table)\b/.test(rest);
      if (!opensEdgeToEdge) {
        const line = source.slice(0, m.index).split('\n').length;
        problems.push(
          `${rel}:${line} <nldd-container> directly in a <nldd-card> without ` +
            'padding: a card has no inset of its own, so the content touches its border.',
        );
      }
    }

    if (
      tag === 'nldd-container' &&
      stack[stack.length - 1] === 'nldd-container' &&
      (!/\b(min-width|max-width|width)="/.test(attrText) || /\bwidth="full"/.test(attrText)) &&
      !/\bclassName="[^"]*\b(row-fill|shrink-0|keep-label-width)\b/.test(attrText) &&
      // The stack only holds nldd-* tags. A <div> or <button> in between (an
      // attachment chip, a thumbnail button) is the real flex item, and the
      // container inside it is sized by that element, not by the wrap.
      !hasElementBetween(source, openIndexByDepth[stack.length - 1], m.index)
    ) {
      const depth = stack.length - 1;
      (fullWidthKids[depth] ??= []).push(source.slice(0, m.index).split('\n').length);
    }

    if (!selfClosing) {
      attrsByDepth[stack.length] = attrText;
      openIndexByDepth[stack.length] = m.index + m[0].length;
      fullWidthKids[stack.length] = [];
      stack.push(tag);
    }
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
