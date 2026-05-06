import { useState, useCallback, useEffect } from 'react';

import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { usePeople } from '@/hooks/usePeople';
import { useAddLeadContact } from '@/hooks/useLeads';
import { useCreateContactPerson } from '@/hooks/useNewContactPerson';
import { NewContactPersonFields } from '@/components/leads/NewContactPersonFields';
import {
  emptyContactPersonFields,
  type ContactPersonFieldsState,
} from '@/components/leads/contactPersonFields';
import { LEAD_CONTACT_ROL_LABELS } from '@/types';

const DEFAULT_CONTACT_ROLLEN: SelectOption[] = Object.entries(
  LEAD_CONTACT_ROL_LABELS,
).map(([value, label]) => ({ value, label }));

interface Props {
  leadId: string | null;
  onClose: () => void;
}

type Mode = 'select' | 'create';

export function AddLeadContactModal({ leadId, onClose }: Props) {
  const { data: people = [] } = usePeople();
  const addContact = useAddLeadContact();
  const createContact = useCreateContactPerson();

  const [mode, setMode] = useState<Mode>('select');
  const [personId, setPersonId] = useState('');
  const [rol, setRol] = useState('contactpersoon');
  const [fields, setFields] = useState<ContactPersonFieldsState>(emptyContactPersonFields);
  const [extraRollen, setExtraRollen] = useState<SelectOption[]>([]);

  const rolOptions: SelectOption[] = [...DEFAULT_CONTACT_ROLLEN, ...extraRollen];

  const handleCreateRol = useCallback(
    async (text: string): Promise<string | null> => {
      const value = text.trim();
      if (!value) return null;
      // Sla de getypte tekst zelf op als rol-waarde. Geen slug-conversie:
      // ResourcePermission.rol is een vrij stringveld en LeadDetailPanel
      // toont de raw waarde als fallback. Een slug zou diakriet/haakjes
      // verminken zonder voordeel.
      setExtraRollen((prev) =>
        prev.some((o) => o.value === value) ||
        DEFAULT_CONTACT_ROLLEN.some((o) => o.value === value)
          ? prev
          : [...prev, { value, label: value }],
      );
      setRol(value);
      return value;
    },
    [],
  );

  // Reset alle state bij elke lead-wissel én bij sluiten van de modal,
  // zodat eerder ingevulde "nieuwe contact"-velden niet doorlekken naar
  // een volgende lead.
  useEffect(() => {
    if (!leadId) return;
    setMode('select');
    setPersonId('');
    setRol('contactpersoon');
    setFields(emptyContactPersonFields());
    setExtraRollen([]);
  }, [leadId]);

  const personOptions: SelectOption[] = people.map((p) => {
    const parts = [p.functie, p.expertise].filter((v): v is string => !!v);
    return {
      value: p.id,
      label: p.naam,
      description: parts.length > 0 ? parts.join(' · ') : undefined,
    };
  });

  const switchToCreate = useCallback((typedName: string) => {
    setMode('create');
    setFields({ ...emptyContactPersonFields(), naam: typedName });
    return null;
  }, []);

  const resetAndClose = useCallback(() => {
    setMode('select');
    setPersonId('');
    setRol('contactpersoon');
    setFields(emptyContactPersonFields());
    setExtraRollen([]);
    onClose();
  }, [onClose]);

  const handleSubmitSelect = useCallback(async () => {
    if (!leadId || !personId) return;
    try {
      await addContact.mutateAsync({ leadId, personId, rol });
      resetAndClose();
    } catch {
      // toast wordt al getoond
    }
  }, [leadId, personId, rol, addContact, resetAndClose]);

  const handleSubmitCreate = useCallback(async () => {
    if (!leadId) return;
    const result = await createContact.create({
      naam: fields.naam,
      email: fields.email,
      phone: fields.phone,
      functie: fields.functie,
      expertise: fields.expertise,
      organisatieEenheidId: fields.organisatieEenheidId || undefined,
      samenwerkingsverbandIds: Array.from(fields.samenwerkingsverbandIds),
    });
    if (!result) return; // toast getoond, modal blijft open
    try {
      await addContact.mutateAsync({ leadId, personId: result.personId, rol });
      resetAndClose();
    } catch {
      // toast
    }
  }, [leadId, fields, rol, createContact, addContact, resetAndClose]);

  const isPending = createContact.isPending || addContact.isPending;

  return (
    <Modal
      open={!!leadId}
      onClose={resetAndClose}
      title={
        mode === 'create' ? 'Nieuwe contactpersoon' : 'Externe contactpersoon toevoegen'
      }
      size="md"
      zIndex={60}
      closeable={!isPending}
      footer={
        mode === 'create' ? (
          <>
            <Button variant="secondary" onClick={() => setMode('select')}>
              Terug
            </Button>
            <Button
              onClick={handleSubmitCreate}
              loading={isPending}
              disabled={!fields.naam.trim()}
            >
              Aanmaken & koppelen
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={resetAndClose}>
              Annuleren
            </Button>
            <Button
              onClick={handleSubmitSelect}
              loading={addContact.isPending}
              disabled={!personId}
            >
              Toevoegen
            </Button>
          </>
        )
      }
    >
      {mode === 'select' ? (
        <div className="space-y-4">
          <CreatableSelect
            label="Persoon"
            value={personId}
            onChange={setPersonId}
            options={personOptions}
            placeholder="Zoek of maak een persoon..."
            onCreate={async (name) => switchToCreate(name)}
            createLabel="Nieuwe persoon aanmaken"
            required
          />
          <CreatableSelect
            label="Rol"
            value={rol}
            onChange={setRol}
            options={rolOptions}
            placeholder="Selecteer of typ een rol..."
            onCreate={handleCreateRol}
            createLabel="Nieuwe rol toevoegen"
          />
        </div>
      ) : (
        <div className="space-y-4">
          <NewContactPersonFields
            state={fields}
            onChange={setFields}
            disabled={isPending}
          />
          <CreatableSelect
            label="Rol op deze lead"
            value={rol}
            onChange={setRol}
            options={rolOptions}
            placeholder="Selecteer of typ een rol..."
            onCreate={handleCreateRol}
            createLabel="Nieuwe rol toevoegen"
          />
        </div>
      )}
    </Modal>
  );
}
