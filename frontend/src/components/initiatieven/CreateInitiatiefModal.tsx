import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import { useCreateInitiatief } from '@/hooks/useInitiatieven';
import { INITIATIEF_COLORS } from '@/types';
import type { InitiatiefCreate, InitiatiefListItem } from '@/types';
import { InitiatiefKleurPicker } from './InitiatiefKleurPicker';

/**
 * Controlled `nldd-text-field` for the new-initiatief naam field, wired
 * directly rather than through the shared `Input` component: `Input`'s
 * `onChange` is not forwarded to its underlying nldd element, so it silently
 * no-ops on every keystroke there.
 */
function InitiatiefNaamField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement & { focus?: () => void }>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  useEffect(() => {
    ref.current?.focus?.();
  }, []);
  return (
    <nldd-text-field
      ref={ref}
      value={value}
      placeholder="Naam van het initiatief"
      required
      accessible-label="Naam"
    />
  );
}

const EMPTY: InitiatiefCreate = { naam: '', beschrijving: '', kleur: INITIATIEF_COLORS[0] };

export function CreateInitiatiefModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (initiatief: InitiatiefListItem | { id: string }) => void;
}) {
  const createInitiatief = useCreateInitiatief();
  const [form, setForm] = useState<InitiatiefCreate>(EMPTY);

  const handleCreate = async () => {
    if (!form.naam.trim()) return;
    const result = await createInitiatief.mutateAsync(form);
    onCreated(result);
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Nieuw initiatief"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={createInitiatief.isPending}>
            Annuleren
          </Button>
          <Button
            onClick={handleCreate}
            loading={createInitiatief.isPending}
            disabled={!form.naam.trim()}
          >
            Aanmaken
          </Button>
        </>
      }
    >
      <nldd-container gap="16">
        <nldd-form-field label="Naam">
          <InitiatiefNaamField value={form.naam} onChange={(v) => setForm((f) => ({ ...f, naam: v }))} />
        </nldd-form-field>
        <RichTextFormField
          label="Beschrijving"
          value={form.beschrijving || ''}
          onChange={(value) => setForm((f) => ({ ...f, beschrijving: value }))}
          rows={3}
          placeholder="Korte beschrijving..."
        />
        <nldd-form-field label="Kleur">
          <InitiatiefKleurPicker value={form.kleur} onChange={(kleur) => setForm((f) => ({ ...f, kleur }))} />
        </nldd-form-field>
      </nldd-container>
    </Modal>
  );
}
