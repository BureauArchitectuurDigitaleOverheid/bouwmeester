import { useState, useEffect, useRef } from 'react';
import { Copy, RefreshCw } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';
import { usePeople, useSearchPeople } from '@/hooks/usePeople';
import { FUNCTIE_LABELS, DIENSTVERBAND_LABELS } from '@/types';
import type { Person, PersonCreate, PersonFormSubmitParams } from '@/types';

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
  onSubmit: (params: PersonFormSubmitParams) => void;
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

  // Search/select existing person state (create mode, non-agent only)
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [naamQuery, setNaamQuery] = useState('');

  const { data: allPeople = [] } = usePeople();
  const { data: searchResults = [] } = useSearchPeople(naamQuery);

  // Cache all persons we've ever seen from search results so lookups
  // remain stable even when the debounced query changes (Fix #3).
  const personCacheRef = useRef<Map<string, Person>>(new Map());
  for (const p of searchResults) {
    personCacheRef.current.set(p.id, p);
  }

  // Filter out agents from search results
  const personResults = searchResults.filter(p => !p.is_agent);

  // Build options for the naam CreatableSelect
  const naamOptions: SelectOption[] = personResults.map(p => ({
    value: p.id,
    label: p.naam,
    description: p.email || undefined,
  }));

  const naamEmptyMessage = naamQuery.length < 2
    ? 'Typ minimaal 2 tekens om te zoeken...'
    : 'Geen personen gevonden';

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
        if (editData.functie) {
          setFunctieOptions((prev) =>
            prev.some((o) => o.value === editData.functie)
              ? prev
              : [...prev, { value: editData.functie!, label: editData.functie! }],
          );
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
        setSelectedPerson(null);
        setNaamQuery('');
        personCacheRef.current.clear();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editData, defaultIsAgent, defaultOrgEenheidId, allPeople]);

  const isAgent = editData ? editData.is_agent : defaultIsAgent;
  const isCreateMode = !editData;
  const isValid = selectedPerson
    ? true // existing person is always valid
    : naam.trim() && (isAgent || email.trim());

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    if (editData) {
      onSubmit({
        kind: 'edit',
        personId: editData.id,
        data: {
          naam: naam.trim(),
          email: email.trim() || undefined,
          functie: isAgent ? undefined : (functie || undefined),
          description: isAgent ? (description.trim() || undefined) : undefined,
          is_agent: isAgent,
          api_key: isAgent ? apiKey : undefined,
        },
      });
    } else if (selectedPerson) {
      onSubmit({
        kind: 'link',
        existingPersonId: selectedPerson.id,
        orgEenheidId: orgEenheidId || undefined,
        dienstverband: orgEenheidId ? dienstverband : undefined,
      });
    } else {
      onSubmit({
        kind: 'create',
        data: {
          naam: naam.trim(),
          email: email.trim() || undefined,
          functie: isAgent ? undefined : (functie || undefined),
          description: isAgent ? (description.trim() || undefined) : undefined,
          is_agent: isAgent,
          api_key: isAgent ? apiKey : undefined,
        },
        orgEenheidId: orgEenheidId || undefined,
        dienstverband: orgEenheidId ? dienstverband : undefined,
      });
    }
  };

  const handleCreateFunctie = async (text: string): Promise<string | null> => {
    const value = text.toLowerCase().replace(/\s+/g, '_');
    setFunctieOptions((prev) => [...prev, { value, label: text }]);
    setFunctie(value);
    return value;
  };

  // Handle selecting an existing person from the search dropdown
  const handleNaamSelect = (personId: string) => {
    // Look up in cache first (stable across debounce cycles), then fallback to current results
    const person = personCacheRef.current.get(personId) || personResults.find(p => p.id === personId);
    if (person) {
      setSelectedPerson(person);
      setNaam(person.naam);
      setEmail(person.email || '');
      setFunctie(person.functie || '');
      // Ensure the functie value is in options
      if (person.functie) {
        setFunctieOptions((prev) =>
          prev.some((o) => o.value === person.functie)
            ? prev
            : [...prev, { value: person.functie!, label: person.functie! }],
        );
      }
    }
  };

  // Handle creating a new person (typed name not found in results)
  const handleNaamCreate = async (text: string): Promise<string | null> => {
    setSelectedPerson(null);
    setNaam(text);
    setEmail('');
    setFunctie('');
    return null; // don't set a value — we switch to create mode
  };

  // Clear selected person and return to search/create mode
  const handleNaamClear = () => {
    setSelectedPerson(null);
    setNaam('');
    setEmail('');
    setFunctie('');
    setNaamQuery('');
  };

  const title = editData
    ? (isAgent ? 'Agent bewerken' : 'Persoon bewerken')
    : selectedPerson
      ? 'Persoon koppelen'
      : (isAgent ? 'Agent toevoegen' : 'Persoon toevoegen');

  const submitLabel = editData
    ? 'Opslaan'
    : selectedPerson
      ? 'Koppelen'
      : 'Toevoegen';

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
            {submitLabel}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Naam field: search+select in create mode for non-agents, plain Input otherwise */}
        {isCreateMode && !isAgent ? (
          <CreatableSelect
            label="Naam"
            value={selectedPerson?.id || ''}
            onChange={handleNaamSelect}
            options={naamOptions}
            placeholder="Zoek persoon of typ nieuwe naam..."
            onCreate={handleNaamCreate}
            createLabel="Nieuwe persoon aanmaken"
            onQueryChange={setNaamQuery}
            filterLocally={false}
            displayValue={naam}
            onClear={selectedPerson ? handleNaamClear : undefined}
            emptyMessage={naamEmptyMessage}
            required
          />
        ) : (
          <Input
            label="Naam"
            value={naam}
            onChange={(e) => setNaam(e.target.value)}
            placeholder="Volledige naam"
            required
            autoFocus
          />
        )}
        {!isAgent && selectedPerson && (
          <Input
            label="E-mail"
            type="email"
            value={email || 'Geen e-mail'}
            onChange={() => {}}
            disabled
          />
        )}
        {!isAgent && !selectedPerson && (
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
            disabled={!!selectedPerson}
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
