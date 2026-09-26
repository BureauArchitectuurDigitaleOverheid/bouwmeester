/**
 * A CSS color as the concrete value the browser resolves it to.
 *
 * SVG presentation attributes are not CSS declarations, and not every browser
 * reads `fill="var(--x)"` (Chrome does, older engines paint the default
 * instead). reactflow writes some colors that way (Background `color`, MiniMap
 * `nodeColor` and `maskColor`), so a design-system token handed to those is
 * resolved first. Everything reactflow puts in a `style` (edge strokes,
 * markers, labels) takes the token as is and needs no help from here.
 *
 * Resolves through a hidden probe's computed `color`, which also settles
 * `light-dark()` and `color-mix()`. Cached per input: the app is light-only for
 * now (see index.css), so a resolved value never goes stale. When it follows
 * the system scheme, clear the cache on a scheme change and re-render the graphs.
 */
const cache = new Map<string, string>();
let probe: HTMLElement | null = null;

export function resolveColor(color: string): string {
  const hit = cache.get(color);
  if (hit !== undefined) return hit;
  if (typeof document === 'undefined') return color;

  if (!probe) {
    probe = document.createElement('span');
    probe.hidden = true;
    probe.setAttribute('aria-hidden', 'true');
    document.body.appendChild(probe);
  }
  probe.style.color = '';
  probe.style.color = color;
  // An empty result means the browser (or jsdom) could not resolve it; the
  // input is the best remaining answer.
  const resolved = getComputedStyle(probe).color || color;
  cache.set(color, resolved);
  return resolved;
}
