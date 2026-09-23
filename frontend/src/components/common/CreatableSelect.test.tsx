import { describe, it, expect, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { CreatableSelect } from './CreatableSelect';

const OPTIONS = [
  { value: 'a', label: 'Dienst Toeslagen' },
  { value: 'b', label: 'Belastingdienst' },
  { value: 'c', label: 'Kadaster' },
];

/**
 * What the browser sends per keystroke: the combo box's own CustomEvent with
 * the typed text, then the native InputEvent from its inner <input>, which is
 * composed and reaches the host too, without a value.
 */
function type(comboBox: Element, text: string) {
  act(() => {
    comboBox.dispatchEvent(new CustomEvent('input', { detail: { value: text } }));
    comboBox.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  });
}

const itemTexts = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-menu-item')].map((i) => i.getAttribute('text'));

describe('CreatableSelect', () => {
  it('filters on what was typed, not on the native event that follows it', () => {
    const { container } = render(
      <CreatableSelect value="" onChange={vi.fn()} options={OPTIONS} />,
    );
    type(container.querySelector('nldd-combo-box')!, 'dienst');
    expect(itemTexts(container)).toEqual(['Dienst Toeslagen', 'Belastingdienst']);
  });

  it('does not clear a chosen value while typing', () => {
    const onClear = vi.fn();
    const { container } = render(
      <CreatableSelect value="c" onChange={vi.fn()} onClear={onClear} options={OPTIONS} />,
    );
    type(container.querySelector('nldd-combo-box')!, 'Kad');
    expect(onClear).not.toHaveBeenCalled();
  });
});
