import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { useOrganisatieFlat, useCreateOrganisatieEenheid } from '@/hooks/useOrganisatie';
import type { Person, PersonCreate } from '@/types';

const DEFAULT_ROL_OPTIONS: SelectOption[] = [
  { value: 'minister', label: 'Minister' },
  { value: 'staatssecretaris', label: 'Staatssecretaris' },
  { value: 'secretaris_generaal', label: 'Secretaris-Generaal' },
  { value: 'directeur_generaal', label: 'Directeur-Generaal' },
  { value: 'directeur', label: 'Directeur' },
  { value: 'afdelingshoofd', label: 'Afdelingshoofd' },
  { value: 'coordinator', label: 'Coordinator' },
  { value: 'beleidsmedewerker', label: 'Beleidsmedewerker' },
  { value: 'senior_beleidsmedewerker', label: 'Senior Beleidsmedewerker' },
  { value: 'adviseur', label: 'Adviseur' },
  { value: 'projectleider', label: 'Projectleider' },
  { value: 'programmamanager', label: 'Programmamanager' },
  { value: 'jurist', label: 'Jurist' },
  { value: 'communicatieadviseur', label: 'Communicatieadviseur' },
];

interface PersonEditFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: PersonCreate) => void;
  isLoading?: boolean;
  editData?: Person | null;
  defaultOrgEenheidId?: string | null;
}

export function PersonEditForm({
  open,
  onClose,
  onSubmit,
  isLoading,
  editData,
  defaultOrgEenheidId,
}: PersonEditFormProps) {
  const [naam, setNaam] = useState('');
  const [email, setEmail] = useState('');
  const [organisatieEenheidId, setOrganisatieEenheidId] = useState('');
  const [afdeling, setAfdeling] = useState('');
  const [functie, setFunctie] = useState('');
  const [rol, setRol] = useState('');
  const [rolOptions, setRolOptions] = useState<SelectOption[]>(DEFAULT_ROL_OPTIONS);

  const { data: orgEenheden = [] } = useOrganisatieFlat();
  const createOrgMutation = useCreateOrganisatieEenheid();

  const orgOptions = orgEenheden.map((e) => ({
    value: e.id,
    label: e.naam,
    description: e.type,
  }));

  useEffect(() => {
    if (open) {
      if (editData) {
        setNaam(editData.naam);
        setEmail(editData.email || '');
        setOrganisatieEenheidId(editData.organisatie_eenheid_id || '');
        setAfdeling(editData.afdeling || '');
        setFunctie(editData.functie || '');
        setRol(editData.rol || '');
        // Ensure the existing rol value is in options
        if (editData.rol && !rolOptions.some((o) => o.value === editData.rol)) {
          setRolOptions((prev) => [...prev, { value: editData.rol!, label: editData.rol! }]);
        }
      } else {
        setNaam('');
        setEmail('');
        setOrganisatieEenheidId(defaultOrgEenheidId || '');
        setAfdeling('');
        setFunctie('');
        setRol('');
      }
    }
  }, [open, editData, defaultOrgEenheidId]);

  const isValid = naam.trim() && email.trim();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    onSubmit({
      naam: naam.trim(),
      email: email.trim(),
      afdeling: afdeling.trim() || undefined,
      functie: functie.trim() || undefined,
      rol: rol || undefined,
      organisatie_eenheid_id: organisatieEenheidId || null,
    });
  };

  const handleCreateOrgEenheid = async (text: string): Promise<string | null> => {
    try {
      const result = await createOrgMutation.mutateAsync({
        naam: text,
        type: 'afdeling',
      });
      return result.id;
    } catch {
      return null;
    }
  };

  const handleCreateRol = async (text: string): Promise<string | null> => {
    const value = text.toLowerCase().replace(/\s+/g, '_');
    setRolOptions((prev) => [...prev, { value, label: text }]);
    setRol(value);
    return value;
  };

  const title = editData ? 'Persoon bewerken' : 'Persoon toevoegen';

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
            disabled={!isValid}
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
          placeholder="Volledige naam"
          required
          autoFocus
        />
        <Input
          label="E-mail"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email@voorbeeld.nl"
          required
        />
        <CreatableSelect
          label="Organisatie-eenheid"
          value={organisatieEenheidId}
          onChange={setOrganisatieEenheidId}
          options={orgOptions}
          placeholder="Selecteer of maak eenheid..."
          onCreate={handleCreateOrgEenheid}
          createLabel="Nieuwe eenheid aanmaken"
        />
        <CreatableSelect
          label="Rol"
          value={rol}
          onChange={setRol}
          options={rolOptions}
          placeholder="Selecteer of maak rol..."
          onCreate={handleCreateRol}
          createLabel="Nieuwe rol aanmaken"
        />
        <Input
          label="Afdeling"
          value={afdeling}
          onChange={(e) => setAfdeling(e.target.value)}
          placeholder="Bijv. Stadsontwikkeling"
        />
        <Input
          label="Functie"
          value={functie}
          onChange={(e) => setFunctie(e.target.value)}
          placeholder="Bijv. Beleidsmedewerker"
        />
      </form>
    </Modal>
  );
}
