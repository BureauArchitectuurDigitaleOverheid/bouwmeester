import { useState, useEffect } from 'react';
import { Copy, RefreshCw } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';
import { usePeople } from '@/hooks/usePeople';
import { FUNCTIE_LABELS, DIENSTVERBAND_LABELS } from '@/types';
import type { Person, PersonCreate } from '@/types';

// Character names from Bordewijk's novel "Karakter" — used as agent names
const KARAKTER_NAMEN = [
  // Hoofdpersonen
  'Dreverhaven', 'Katadreuffe', 'Joba',
  // Kantoor & juridisch
  'Stroomkoning', 'De Gankelaar', 'Rentenstein', 'Carlion', 'Schuwagt',
  'Lorna te George', 'Graanoogst', 'Piaat',
  // Overige personages
  'Jan Maan', 'Harm Knol Hein', 'De Merree', 'Kalvelage', 'Sibculo',
  'Hamerslag', 'Den Hieperboree', 'Wever', 'Kees Adam',
  'Burgeik', 'Van den Born', 'Iris',
];

function generateMockApiKey(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  const segments = [8, 4, 4, 4, 12];
  return 'bm_' + segments.map(len =>
    Array.from({ length: len }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
  ).join('-');
}

const DEFAULT_FUNCTIE_OPTIONS: SelectOption[] = Object.entries(FUNCTIE_LABELS).map(
  ([value, label]) => ({ value, label })
);

interface PersonEditFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: PersonCreate, orgEenheidId?: string, dienstverband?: string) => void;
  isLoading?: boolean;
  editData?: Person | null;
  defaultIsAgent?: boolean;
  /** Pre-fill the org unit selector (e.g. when adding from within an org unit) */
  defaultOrgEenheidId?: string;
}

export function PersonEditForm({
  open,
  onClose,
  onSubmit,
  isLoading,
  editData,
  defaultIsAgent = false,
  defaultOrgEenheidId,
}: PersonEditFormProps) {
  const [naam, setNaam] = useState('');
  const [email, setEmail] = useState('');
  const [functie, setFunctie] = useState('');
  const [description, setDescription] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [orgEenheidId, setOrgEenheidId] = useState('');
  const [dienstverband, setDienstverband] = useState('in_dienst');
  const [functieOptions, setFunctieOptions] = useState<SelectOption[]>(DEFAULT_FUNCTIE_OPTIONS);

  const { data: allPeople = [] } = usePeople();

  useEffect(() => {
    if (open) {
      if (editData) {
        setNaam(editData.naam);
        setEmail(editData.email || '');
        setFunctie(editData.functie || '');
        setDescription(editData.description || '');
        setApiKey(editData.api_key || '');
        setOrgEenheidId('');
        // Ensure the existing functie value is in options
        if (editData.functie && !functieOptions.some((o) => o.value === editData.functie)) {
          setFunctieOptions((prev) => [...prev, { value: editData.functie!, label: editData.functie! }]);
        }
      } else {
        // For new agents, pick next available Karakter name
        if (defaultIsAgent) {
          const usedNames = new Set(allPeople.filter(p => p.is_agent).map(p => p.naam));
          const nextName = KARAKTER_NAMEN.find(n => !usedNames.has(n)) || '';
          setNaam(nextName);
        } else {
          setNaam('');
        }
        setEmail('');
        setFunctie('');
        setDescription('');
        setApiKey(defaultIsAgent ? generateMockApiKey() : '');
        setOrgEenheidId(defaultOrgEenheidId || '');
        setDienstverband('in_dienst');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editData]);

  const isAgent = editData ? editData.is_agent : defaultIsAgent;
  const isValid = naam.trim() && (isAgent || email.trim());

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    onSubmit(
      {
        naam: naam.trim(),
        email: email.trim() || undefined,
        functie: isAgent ? undefined : (functie || undefined),
        description: isAgent ? (description.trim() || undefined) : undefined,
        is_agent: isAgent,
        api_key: isAgent ? apiKey : undefined,
      },
      orgEenheidId || undefined,
      orgEenheidId ? dienstverband : undefined,
    );
  };

  const handleCreateFunctie = async (text: string): Promise<string | null> => {
    const value = text.toLowerCase().replace(/\s+/g, '_');
    setFunctieOptions((prev) => [...prev, { value, label: text }]);
    setFunctie(value);
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
          <>
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
            <div>
              <label className="block text-sm font-medium text-text mb-1">Beschrijving</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Wat doet deze agent?"
                rows={3}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm text-text placeholder:text-text-secondary/50 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              />
            </div>
          </>
        )}
        {!isAgent && (
          <CreatableSelect
            label="Functie"
            value={functie}
            onChange={setFunctie}
            options={functieOptions}
            placeholder="Selecteer of maak functie..."
            onCreate={handleCreateFunctie}
            createLabel="Nieuwe functie aanmaken"
          />
        )}
        {!editData && (
          <CascadingOrgSelect
            value={orgEenheidId}
            onChange={setOrgEenheidId}
          />
        )}
        {!editData && orgEenheidId && (
          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Dienstverband
            </label>
            <select
              value={dienstverband}
              onChange={(e) => setDienstverband(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm text-text bg-white focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
            >
              {Object.entries(DIENSTVERBAND_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        )}
      </form>
    </Modal>
  );
}
