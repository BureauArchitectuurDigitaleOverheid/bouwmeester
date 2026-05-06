/**
 * Velden voor het aanmaken van een nieuwe externe contactpersoon.
 *
 * Pure render-component (geen submit-logica). Wordt gebruikt door
 * AddLeadContactModal, LeadDetailPanel (inline contact) en
 * LeadIntakeDialog zodat alle drie de flows dezelfde set velden bieden.
 */

import { useMemo, useState } from 'react';

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
      <div>
        <label className="block text-sm font-medium text-text mb-1">
          Organisatie-eenheid (optioneel)
        </label>
        <CascadingOrgSelect
          value={state.organisatieEenheidId}
          onChange={(v) => set('organisatieEenheidId', v)}
        />
      </div>
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
    <div>
      <label className="block text-sm font-medium text-text mb-1">
        Samenwerkingsverbanden (optioneel)
      </label>
      <div className="max-h-32 overflow-y-auto rounded-lg border border-border p-2 space-y-1">
        {samenwerkingsverbanden.map((s) => (
          <label
            key={s.id}
            className={`flex items-center gap-2 text-sm rounded px-1 py-0.5 ${
              disabled
                ? 'cursor-not-allowed opacity-60'
                : 'cursor-pointer hover:bg-gray-50'
            }`}
          >
            <input
              type="checkbox"
              checked={selected.has(s.id)}
              onChange={() => onToggle(s.id)}
              className="rounded border-border"
              disabled={disabled}
            />
            <span className="flex-1 truncate">{s.naam}</span>
            <span className="text-xs text-text-secondary shrink-0">
              {SAMENWERKINGSVERBAND_TYPE_LABELS[s.type] ?? s.type}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
