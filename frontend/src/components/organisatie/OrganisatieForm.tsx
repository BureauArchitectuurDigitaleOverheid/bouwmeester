import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { RichTextEditor } from '@/components/common/RichTextEditor';
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editData, defaultParentId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!naam.trim() || !type) return;

    // Detect empty TipTap document — treat as null
    let cleanBeschrijving: string | null = beschrijving.trim() || null;
    if (cleanBeschrijving) {
      try {
        const parsed = JSON.parse(cleanBeschrijving);
        if (
          parsed?.type === 'doc' &&
          Array.isArray(parsed.content) &&
          parsed.content.length <= 1 &&
          (!parsed.content[0]?.content || parsed.content[0].content.length === 0)
        ) {
          cleanBeschrijving = null;
        }
      } catch {
        // plain text — keep as-is
      }
    }

    onSubmit({
      naam: naam.trim(),
      type,
      parent_id: parentId || null,
      manager_id: managerId || null,
      beschrijving: cleanBeschrijving,
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
          <RichTextEditor
            value={beschrijving}
            onChange={setBeschrijving}
            placeholder="Optionele beschrijving... Gebruik @ voor personen, # voor nodes/taken"
            rows={3}
          />
        </div>
      </form>
    </Modal>
  );
}
