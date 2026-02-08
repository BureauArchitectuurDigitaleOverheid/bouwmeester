import { useState, useEffect } from 'react';
import { Copy, RefreshCw } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { useOrganisatieFlat, useCreateOrganisatieEenheid } from '@/hooks/useOrganisatie';
import type { Person, PersonCreate } from '@/types';

function generateMockApiKey(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  const segments = [8, 4, 4, 4, 12];
  return 'bm_' + segments.map(len =>
    Array.from({ length: len }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
  ).join('-');
}

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
  defaultIsAgent?: boolean;
}

export function PersonEditForm({
  open,
  onClose,
  onSubmit,
  isLoading,
  editData,
  defaultOrgEenheidId,
  defaultIsAgent = false,
}: PersonEditFormProps) {
  const [naam, setNaam] = useState('');
  const [email, setEmail] = useState('');
  const [organisatieEenheidId, setOrganisatieEenheidId] = useState('');
  const [afdeling, setAfdeling] = useState('');
  const [functie, setFunctie] = useState('');
  const [rol, setRol] = useState('');
  const [apiKey, setApiKey] = useState('');
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
        setApiKey(editData.api_key || '');
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
        setApiKey(defaultIsAgent ? generateMockApiKey() : '');
      }
    }
  }, [open, editData, defaultOrgEenheidId]);

  const isAgent = editData ? editData.is_agent : defaultIsAgent;
  const isValid = naam.trim() && (isAgent || email.trim());

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    onSubmit({
      naam: naam.trim(),
      email: email.trim() || undefined,
      afdeling: afdeling.trim() || undefined,
      functie: functie.trim() || undefined,
      rol: rol || undefined,
      organisatie_eenheid_id: organisatieEenheidId || null,
      is_agent: isAgent,
      api_key: isAgent ? apiKey : undefined,
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

  const title = editData
    ? (isAgent ? 'Agent bewerken' : 'Persoon bewerken')
    : (isAgent ? 'Agent toevoegen' : 'Persoon toevoegen');

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
        {!isAgent && (
          <Input
            label="E-mail"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@voorbeeld.nl"
            required
          />
        )}
        {isAgent && (
          <div>
            <label className="block text-sm font-medium text-text mb-1">API Key</label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={apiKey}
                className="flex-1 rounded-lg border border-border bg-gray-50 px-3 py-2 text-sm font-mono text-text-secondary"
              />
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(apiKey)}
                className="flex items-center justify-center h-9 w-9 rounded-lg border border-border hover:bg-gray-50 transition-colors"
                title="Kopieer API key"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setApiKey(generateMockApiKey())}
                className="flex items-center justify-center h-9 w-9 rounded-lg border border-border hover:bg-gray-50 transition-colors"
                title="Genereer nieuwe API key"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
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
