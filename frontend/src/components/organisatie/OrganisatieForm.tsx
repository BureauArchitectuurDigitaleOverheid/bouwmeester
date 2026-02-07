import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import type {
  OrganisatieEenheid,
  OrganisatieEenheidCreate,
  OrganisatieEenheidUpdate,
} from '@/types';
import { ORGANISATIE_TYPE_OPTIONS } from '@/types';
import { useOrganisatieFlat, useOrganisatiePersonen } from '@/hooks/useOrganisatie';

interface OrganisatieFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: OrganisatieEenheidCreate | OrganisatieEenheidUpdate) => void;
  isLoading?: boolean;
  /** If provided, the form is in edit mode */
  editData?: OrganisatieEenheid | null;
  /** Pre-fill parent_id for adding a child */
  defaultParentId?: string | null;
}

export function OrganisatieForm({
  open,
  onClose,
  onSubmit,
  isLoading,
  editData,
  defaultParentId,
}: OrganisatieFormProps) {
  const [naam, setNaam] = useState('');
  const [type, setType] = useState('');
  const [parentId, setParentId] = useState<string>('');
  const [managerId, setManagerId] = useState<string>('');
  const [beschrijving, setBeschrijving] = useState('');
  const [typeOptions, setTypeOptions] = useState<SelectOption[]>(
    ORGANISATIE_TYPE_OPTIONS.map((o) => ({ ...o })),
  );

  const { data: flatList = [] } = useOrganisatieFlat();
  const { data: personen = [] } = useOrganisatiePersonen(editData?.id ?? null);

  // Parent options from flat list, excluding self (in edit mode)
  const parentOptions: SelectOption[] = [
    { value: '', label: 'Geen (top-niveau)' },
    ...flatList
      .filter((e) => !editData || e.id !== editData.id)
      .map((e) => ({
        value: e.id,
        label: e.naam,
        description: e.type,
      })),
  ];

  // Manager options from people in this unit
  const managerOptions: SelectOption[] = [
    { value: '', label: 'Geen manager' },
    ...personen.map((p) => ({
      value: p.id,
      label: p.naam,
      description: p.functie || undefined,
    })),
  ];

  useEffect(() => {
    if (open) {
      if (editData) {
        setNaam(editData.naam);
        setType(editData.type);
        setParentId(editData.parent_id || '');
        setManagerId(editData.manager_id || '');
        setBeschrijving(editData.beschrijving || '');
        // Make sure the type is in options
        if (!typeOptions.some((o) => o.value === editData.type)) {
          setTypeOptions((prev) => [
            ...prev,
            { value: editData.type, label: editData.type },
          ]);
        }
      } else {
        setNaam('');
        setType('');
        setParentId(defaultParentId || '');
        setManagerId('');
        setBeschrijving('');
      }
    }
  }, [open, editData, defaultParentId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!naam.trim() || !type) return;

    onSubmit({
      naam: naam.trim(),
      type,
      parent_id: parentId || null,
      manager_id: managerId || null,
      beschrijving: beschrijving.trim() || null,
    });
  };

  const handleCreateType = async (text: string): Promise<string | null> => {
    const value = text.toLowerCase().replace(/\s+/g, '_');
    setTypeOptions((prev) => [...prev, { value, label: text }]);
    setType(value);
    return value;
  };

  const title = editData ? 'Eenheid bewerken' : 'Eenheid toevoegen';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            onClick={handleSubmit}
            loading={isLoading}
            disabled={!naam.trim() || !type}
          >
            {editData ? 'Opslaan' : 'Toevoegen'}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Naam"
          value={naam}
          onChange={(e) => setNaam(e.target.value)}
          placeholder="Bijv. Directie Openbaar Vervoer"
          required
          autoFocus
        />

        <CreatableSelect
          label="Type"
          value={type}
          onChange={setType}
          options={typeOptions}
          placeholder="Selecteer of maak type..."
          onCreate={handleCreateType}
          createLabel="Nieuw type aanmaken"
          required
        />

        <CreatableSelect
          label="Bovenliggende eenheid"
          value={parentId}
          onChange={setParentId}
          options={parentOptions}
          placeholder="Selecteer bovenliggende eenheid..."
        />

        {editData && (
          <CreatableSelect
            label="Manager"
            value={managerId}
            onChange={setManagerId}
            options={managerOptions}
            placeholder="Selecteer manager..."
          />
        )}

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-text">Beschrijving</label>
          <textarea
            value={beschrijving}
            onChange={(e) => setBeschrijving(e.target.value)}
            placeholder="Optionele beschrijving van deze organisatie-eenheid..."
            rows={3}
            className="block w-full rounded-xl border border-border bg-white px-3.5 py-2.5 text-sm text-text placeholder:text-text-secondary/50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 hover:border-border-hover"
          />
        </div>
      </form>
    </Modal>
  );
}
