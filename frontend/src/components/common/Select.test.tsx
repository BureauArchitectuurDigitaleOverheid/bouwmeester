import { describe, it, expect, vi, beforeAll } from 'vitest';
import { act, render } from '@testing-library/react';
import { Select } from './Select';

/**
 * Tegen de échte `nldd-dropdown`, want de bug zit in die component en een
 * stub zou hem wegpoetsen.
 *
 * Het zichtbare label is een `<span>` in de shadow-DOM, met de echte
 * `<select>` er op `opacity: 0` overheen. Die span wordt gevuld door
 * `_syncDisplayValue()`, en dat draait alleen bij `slotchange` en bij een
 * `change` van de gebruiker. Een waarde die programmatisch wordt gezet
 * raakt geen van beide, dus het label bleef staan op de optie van het
 * mounten: een opgeslagen drempel van 20 las als "Alles tonen".
 *
 * De mount-case is in jsdom niet te vangen (daar landt `slotchange` ná de
 * waarde die React zet, en dan klopt het label vanzelf). De post-mount case
 * wél, en dat is het geval uit productie.
 */
beforeAll(async () => {
  await import('@nldd/design-system/dropdown');
});

const DREMPELS = [
  { value: '0', label: 'Alles tonen' },
  { value: '20', label: 'Normaal' },
  { value: '40', label: 'Alleen relevante' },
];

const label = (container: HTMLElement) =>
  (container.querySelector('nldd-dropdown') as unknown as { _displayValue?: string })
    ?._displayValue ?? '';

describe('Select', () => {
  it('werkt het zichtbare label bij als de waarde van buitenaf verandert', async () => {
    const { container, rerender } = render(
      <Select value="0" onChange={vi.fn()} options={DREMPELS} aria-label="Drempel" />,
    );

    await act(async () => {
      rerender(<Select value="20" onChange={vi.fn()} options={DREMPELS} aria-label="Drempel" />);
    });

    expect(container.querySelector('select')!.value).toBe('20');
    expect(label(container)).toBe('Normaal');
  });

  it('schrijft niets weg bij het bijwerken van het label', async () => {
    // De dropdown stuurt op een `change` zijn eigen CustomEvent, die bij ons
    // als gebruikersactie binnenkomt. Zonder de vlag zou het rechtzetten van
    // het label een waarde wegschrijven die niemand heeft gekozen.
    const onChange = vi.fn();
    const { rerender } = render(
      <Select value="0" onChange={onChange} options={DREMPELS} aria-label="Drempel" />,
    );

    await act(async () => {
      rerender(<Select value="20" onChange={onChange} options={DREMPELS} aria-label="Drempel" />);
    });

    expect(onChange).not.toHaveBeenCalled();
  });

  it('meldt een keuze van de gebruiker wel', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <Select value="20" onChange={onChange} options={DREMPELS} aria-label="Drempel" />,
    );

    const select = container.querySelector('select')!;
    await act(async () => {
      select.value = '40';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].target.value).toBe('40');
  });
});
