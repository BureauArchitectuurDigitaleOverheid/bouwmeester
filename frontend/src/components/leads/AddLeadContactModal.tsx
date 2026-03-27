import { useState, useCallback } from 'react';

import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { usePeople, useCreatePerson } from '@/hooks/usePeople';
import { useAddLeadContact } from '@/hooks/useLeads';
import { LEAD_CONTACT_ROL_LABELS } from '@/types';

const CONTACT_ROLLEN: SelectOption[] = Object.entries(LEAD_CONTACT_ROL_LABELS).map(
  ([value, label]) => ({ value, label }),
);

interface Props {
  leadId: string | null;
  onClose: () => void;
}

export function AddLeadContactModal({ leadId, onClose }: Props) {
  const { data: people = [] } = usePeople();
  const createPerson = useCreatePerson();
  const addContact = useAddLeadContact();

  const [personId, setPersonId] = useState('');
  const [rol, setRol] = useState('contactpersoon');

  const personOptions: SelectOption[] = people.map((p) => ({
    value: p.id,
    label: p.naam,
    description: p.functie ?? undefined,
  }));

  const handleCreatePerson = useCallback(
    async (name: string): Promise<string | null> => {
      const result = await createPerson.mutateAsync({ naam: name });
      return result?.id ?? null;
    },
    [createPerson],
  );

  const resetAndClose = useCallback(() => {
    setPersonId('');
    setRol('contactpersoon');
    onClose();
  }, [onClose]);

  const handleSubmit = useCallback(async () => {
    if (!leadId || !personId) return;
    try {
      await addContact.mutateAsync({ leadId, personId, rol });
      resetAndClose();
    } catch {
      // useMutationWithError already shows a toast; keep modal open so the user can retry
    }
  }, [leadId, personId, rol, addContact, resetAndClose]);

  return (
    <Modal
      open={!!leadId}
      onClose={resetAndClose}
      title="Contact toevoegen"
      size="sm"
      zIndex={60}
      footer={
        <>
          <Button variant="secondary" onClick={resetAndClose}>
            Annuleren
          </Button>
          <Button onClick={handleSubmit} loading={addContact.isPending} disabled={!personId}>
            Toevoegen
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <CreatableSelect
          label="Persoon"
          value={personId}
          onChange={setPersonId}
          options={personOptions}
          placeholder="Zoek of maak een persoon..."
          onCreate={handleCreatePerson}
          createLabel="Nieuwe persoon aanmaken"
          required
        />
        <CreatableSelect
          label="Rol"
          value={rol}
          onChange={setRol}
          options={CONTACT_ROLLEN}
          placeholder="Selecteer een rol..."
          searchable={false}
        />
      </div>
    </Modal>
  );
}
