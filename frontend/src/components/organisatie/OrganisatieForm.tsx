import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import type {
  OrganisatieEenheid,
  OrganisatieEenheidCreate,
  OrganisatieEenheidUpdate,
} from '@/types';
import { ORGANISATIE_TYPE_OPTIONS, formatFunctie } from '@/types';
import { useOrganisatieFlat, useOrganisatiePersonen } from '@/hooks/useOrganisatie';
import { useCan } from '@/hooks/useCan';
import { NlddButton } from '@/components/nldd/NlddButton';

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
  // Naming a manager is a role assignment on this eenheid; the backend's
  // grant authority decides (only asked when editing, the field is hidden
  // on create).
  const { allowed: canSetManager } = useCan(
    'eenheid:set_manager',
    editData ? { type: 'organisatie_eenheid', id: editData.id } : null,
  );
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
      description: formatFunctie(p.functie),
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

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
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
      // Only send a manager when this person may name one; otherwise the
      // backend would read an unchanged value as an attempt to set it.
      ...(canSetManager ? { manager_id: managerId || null } : {}),
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
          <NlddButton variant="secondary" onClick={onClose} text="Annuleren" />
          <NlddButton
            onClick={handleSubmit}
            loading={isLoading}
            disabled={!naam.trim() || !type}
            text={editData ? 'Opslaan' : 'Toevoegen'}
          />
        </>
      }
    >
      {/*
        Submit/cancel live in Modal's `footer`, a sibling of `children` — not
        a descendant of nldd-form, so nldd-form-actions cannot reach them
        from here. Wrapping the body still gets autofill and label-alignment
        inheritance for the fields.
      */}
      <nldd-form>
      <form onSubmit={handleSubmit}>
      <nldd-container layout="stack" gap="16">
        <Input
          label="Naam"
          value={naam}
          onChange={(e) => setNaam(e.target.value)}
          placeholder="Bijv. Directie Openbaar Vervoer"
          autoComplete="organization"
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

        {editData && canSetManager && (
          <CreatableSelect
            label={type === 'cluster' || type === 'team' ? 'Coördinator' : 'Manager'}
            value={managerId}
            onChange={setManagerId}
            options={managerOptions}
            placeholder={type === 'cluster' || type === 'team' ? 'Selecteer coördinator...' : 'Selecteer manager...'}
          />
        )}

        <RichTextFormField label="Beschrijving" value={beschrijving} onChange={setBeschrijving} />
      </nldd-container>
      </form>
      </nldd-form>
    </Modal>
  );
}
