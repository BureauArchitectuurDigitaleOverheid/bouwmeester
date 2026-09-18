/**
 * Velden voor het aanmaken van een nieuwe externe contactpersoon.
 *
 * Pure render-component (geen submit-logica). Wordt gebruikt door
 * AddLeadContactModal, LeadDetailPanel (inline contact) en
 * LeadIntakeDialog zodat alle drie de flows dezelfde set velden bieden.
 */

import { useCallback, useMemo, useRef, useState } from 'react';

import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Input } from '@/components/common/Input';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';
import { useExpertiseValues } from '@/hooks/usePeople';
import { useSamenwerkingsverbanden } from '@/hooks/useSamenwerkingsverbanden';
import {
  SAMENWERKINGSVERBAND_TYPE_LABELS,
  type Samenwerkingsverband,
} from '@/types';
import type { ContactPersonFieldsState } from './contactPersonFields';

interface Props {
  state: ContactPersonFieldsState;
  onChange: (next: ContactPersonFieldsState) => void;
  /** Verberg het naam-veld (gebruikt door AddLeadContactModal waar de naam
   *  uit de zoekbalk komt). */
  hideNaam?: boolean;
  /** Disable alle velden (bv. terwijl een mutation pending is). */
  disabled?: boolean;
  /** Optioneel: gedeelde lijst van extra (lokaal toegevoegde) expertise-
   *  waarden. Wanneer meerdere instances naast elkaar bestaan (bv. in
   *  LeadIntakeDialog) zorgt dit dat een nieuwe waarde direct in alle
   *  rijen verschijnt. Zonder deze props valt het component terug op
   *  per-instance lokale state. */
  extraExpertiseValues?: string[];
  onAddExtraExpertise?: (value: string) => void;
}

export function NewContactPersonFields({
  state,
  onChange,
  hideNaam = false,
  disabled = false,
  extraExpertiseValues,
  onAddExtraExpertise,
}: Props) {
  const { data: expertiseValues = [] } = useExpertiseValues();
  const { data: samenwerkingsverbanden = [] } = useSamenwerkingsverbanden({
    actief: true,
  });
  const [localAdded, setLocalAdded] = useState<string[]>([]);
  const sharedAdded = extraExpertiseValues ?? localAdded;

  const expertiseOptions: SelectOption[] = useMemo(
    () => [
      ...expertiseValues.map((v) => ({ value: v, label: v })),
      ...sharedAdded
        .filter((v) => !expertiseValues.includes(v))
        .map((v) => ({ value: v, label: v })),
    ],
    [expertiseValues, sharedAdded],
  );

  const set = <K extends keyof ContactPersonFieldsState>(
    key: K,
    value: ContactPersonFieldsState[K],
  ) => onChange({ ...state, [key]: value });

  const toggleSwv = (id: string) => {
    const next = new Set(state.samenwerkingsverbandIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    set('samenwerkingsverbandIds', next);
  };

  return (
    <div className="space-y-4">
      {!hideNaam && (
        <Input
          label="Naam"
          value={state.naam}
          onChange={(e) => set('naam', e.target.value)}
          required
          autoFocus
          disabled={disabled}
        />
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input
          label="E-mail"
          type="email"
          value={state.email}
          onChange={(e) => set('email', e.target.value)}
          placeholder="email@voorbeeld.nl"
          disabled={disabled}
        />
        <Input
          label="Telefoon"
          type="tel"
          value={state.phone}
          onChange={(e) => set('phone', e.target.value)}
          placeholder="06-12345678"
          disabled={disabled}
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input
          label="Functie"
          value={state.functie}
          onChange={(e) => set('functie', e.target.value)}
          placeholder="bv. wetgevingsjurist"
          disabled={disabled}
        />
        <CreatableSelect
          label="Expertise"
          value={state.expertise}
          onChange={(v) => set('expertise', v)}
          options={expertiseOptions}
          placeholder="Bijv. wetgevingsjurist, BIT-adviseur..."
          onCreate={async (text) => {
            const value = text.trim();
            if (!value) return null;
            if (onAddExtraExpertise) {
              onAddExtraExpertise(value);
            } else {
              setLocalAdded((prev) =>
                prev.includes(value) ? prev : [...prev, value],
              );
            }
            set('expertise', value);
            return value;
          }}
          createLabel="Nieuwe expertise toevoegen"
          disabled={disabled}
        />
      </div>
      <CascadingOrgSelect
        label="Organisatie-eenheid (optioneel)"
        value={state.organisatieEenheidId}
        onChange={(v) => set('organisatieEenheidId', v)}
      />
      {samenwerkingsverbanden.length > 0 && (
        <SwvCheckboxList
          samenwerkingsverbanden={samenwerkingsverbanden}
          selected={state.samenwerkingsverbandIds}
          onToggle={toggleSwv}
          disabled={disabled}
        />
      )}
    </div>
  );
}

interface SwvListProps {
  samenwerkingsverbanden: Samenwerkingsverband[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  disabled: boolean;
}

function SwvCheckboxList({
  samenwerkingsverbanden,
  selected,
  onToggle,
  disabled,
}: SwvListProps) {
  return (
    <nldd-form-field label="Samenwerkingsverbanden (optioneel)">
      <nldd-list variant="box-tinted" dividers="always" height="8rem" accessible-label="Samenwerkingsverbanden">
        {samenwerkingsverbanden.map((s) => (
          <SwvCheckboxRow
            key={s.id}
            label={s.naam}
            supportingText={SAMENWERKINGSVERBAND_TYPE_LABELS[s.type] ?? s.type}
            checked={selected.has(s.id)}
            disabled={disabled}
            onToggle={() => onToggle(s.id)}
          />
        ))}
      </nldd-list>
    </nldd-form-field>
  );
}

interface SwvCheckboxRowProps {
  label: string;
  supportingText: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}

function SwvCheckboxRow({ label, supportingText, checked, disabled, onToggle }: SwvCheckboxRowProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', useCallback(() => onToggle(), [onToggle]));

  return (
    <nldd-list-item ref={ref} checkbox checked={orUndef(checked)} {...(disabled ? { disabled: true } : {})}>
      <nldd-text-cell text={label} supporting-text={supportingText} />
    </nldd-list-item>
  );
}
