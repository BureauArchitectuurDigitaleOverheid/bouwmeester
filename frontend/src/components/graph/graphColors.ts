import { entityColorVar } from '@/types';

/**
 * The neutral colors both reactflow canvases (CorpusGraph, LeadGraphView)
 * share: the chrome around the typed nodes and edges.
 *
 * Everything here goes into a `style` except GRID_COLOR and MINIMAP_MASK_COLOR,
 * which reactflow writes as SVG attributes; pass those through `resolveColor`.
 */

/** An untyped edge and its arrowhead. */
export const EDGE_COLOR = entityColorVar('coolgray', 400);

export const EDGE_LABEL_COLOR = 'var(--semantics-content-secondary-color)';

/** Behind an edge label, so the line does not run through the text. */
export const EDGE_LABEL_BG_COLOR = 'var(--semantics-surfaces-base-background-color)';

/** The dot grid on the canvas. SVG attribute: resolve before use. */
export const GRID_COLOR = 'var(--semantics-dividers-color)';

/** Border of the controls and the minimap floating on the canvas. */
export const FLOATING_PANEL_BORDER = '1px solid var(--semantics-dividers-color)';

/** The minimap's dim over what is out of view. SVG attribute: resolve before use. */
export const MINIMAP_MASK_COLOR =
  'color-mix(in oklch, var(--semantics-surfaces-tinted-background-color) 70%, transparent)';
