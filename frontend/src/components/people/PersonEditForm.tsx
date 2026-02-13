import { useState, useEffect, useRef } from 'react';
import { Copy, RefreshCw, Check, Eye, EyeOff, Mail, Phone, Star, X, Plus } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';
import {
  usePeople,
  usePerson,
  useSearchPeople,
  useRotateApiKey,
  useAddPersonEmail,
  useRemovePersonEmail,
  useSetDefaultEmail,
  useAddPersonPhone,
  useRemovePersonPhone,
  useSetDefaultPhone,
} from '@/hooks/usePeople';
import { FUNCTIE_LABELS, DIENSTVERBAND_LABELS, PHONE_LABELS } from '@/types';
import type { Person, PersonFormSubmitParams } from '@/types';

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
  /** One-time API key to display after creation */
  createdApiKey?: string | null;
}

export function PersonEditForm({
  open,
  onClose,
  onSubmit,
  isLoading,
  editData,
  defaultIsAgent = false,
  defaultOrgEenheidId,
  createdApiKey,
}: PersonEditFormProps) {
  const [naam, setNaam] = useState('');
  const [email, setEmail] = useState('');
  const [functie, setFunctie] = useState('');
  const [description, setDescription] = useState('');
  const [orgEenheidId, setOrgEenheidId] = useState('');
  const [dienstverband, setDienstverband] = useState('in_dienst');
  const [emailTouched, setEmailTouched] = useState(false);
  const [functieOptions, setFunctieOptions] = useState<SelectOption[]>(DEFAULT_FUNCTIE_OPTIONS);

  // Rotated API key one-time display
  const [rotatedApiKey, setRotatedApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [confirmRotate, setConfirmRotate] = useState(false);
  const rotateApiKeyMutation = useRotateApiKey();

  // Search/select existing person state (create mode, non-agent only)
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [naamQuery, setNaamQuery] = useState('');

  // Email/phone inline management state (edit mode)
  const [newEmail, setNewEmail] = useState('');
  const [newEmailError, setNewEmailError] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newPhoneLabel, setNewPhoneLabel] = useState('werk');
  const [newPhoneError, setNewPhoneError] = useState('');

  const { data: allPeople = [] } = usePeople();
  const { data: searchResults = [] } = useSearchPeople(naamQuery);
  const { data: freshPerson } = usePerson(editData?.id ?? null);

  // Email/phone mutation hooks
  const addEmailMutation = useAddPersonEmail();
  const removeEmailMutation = useRemovePersonEmail();
  const setDefaultEmailMutation = useSetDefaultEmail();
  const addPhoneMutation = useAddPersonPhone();
  const removePhoneMutation = useRemovePersonPhone();
  const setDefaultPhoneMutation = useSetDefaultPhone();

  // Use fresh person data for emails/phones (auto-refreshed by React Query invalidation)
  const personEmails = freshPerson?.emails ?? editData?.emails ?? [];
  const personPhones = freshPerson?.phones ?? editData?.phones ?? [];

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
    description: p.default_email || p.email || undefined,
  }));

  const naamEmptyMessage = naamQuery.length < 2
    ? 'Typ minimaal 2 tekens om te zoeken...'
    : 'Geen personen gevonden';

  // The key to display — either freshly rotated, freshly created, or nothing.
  const displayApiKey = rotatedApiKey || createdApiKey || null;

  useEffect(() => {
    if (open) {
      setRotatedApiKey(null);
      setCopied(false);
      setShowKey(false);
      setConfirmRotate(false);
      setNewEmail('');
      setNewEmailError('');
      setNewPhone('');
      setNewPhoneLabel('werk');
      setNewPhoneError('');
      if (editData) {
        setNaam(editData.naam);
        setEmail(editData.email || '');
        setFunctie(editData.functie || '');
        setDescription(editData.description || '');
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
        setOrgEenheidId(defaultOrgEenheidId || '');
        setDienstverband('in_dienst');
        setSelectedPerson(null);
        setNaamQuery('');
        setEmailTouched(false);
        personCacheRef.current.clear();
      }
    }
  }, [open, editData, defaultIsAgent, defaultOrgEenheidId, allPeople]);

  const isAgent = editData ? editData.is_agent : defaultIsAgent;
  const isCreateMode = !editData;
  const isEditMode = !!editData;

  const isValid = selectedPerson
    ? true // existing person is always valid
    : isEditMode
      ? !!naam.trim() // edit mode: only naam required (emails managed separately)
      : naam.trim() && (isAgent || email.trim()); // create mode: naam + email (unless agent)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    if (editData) {
      onSubmit({
        kind: 'edit',
        personId: editData.id,
        data: {
          naam: naam.trim(),
          // In edit mode, don't send email — managed via multi-email section
          functie: isAgent ? undefined : (functie || undefined),
          description: isAgent ? (description.trim() || undefined) : undefined,
          is_agent: isAgent,
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
      setEmail(person.default_email || person.email || '');
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

  const handleCopyKey = async () => {
    if (displayApiKey) {
      try {
        await navigator.clipboard.writeText(displayApiKey);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        // Fallback: select the text so user can copy manually
        setShowKey(true);
      }
    }
  };

  const handleRotateKey = async () => {
    if (!editData) return;
    if (!confirmRotate) {
      setConfirmRotate(true);
      return;
    }
    try {
      const result = await rotateApiKeyMutation.mutateAsync(editData.id);
      setRotatedApiKey(result.api_key);
      setCopied(false);
      setConfirmRotate(false);
    } catch {
      setConfirmRotate(false);
    }
  };

  // Email management handlers
  const handleAddEmail = async () => {
    if (!editData || !newEmail.trim()) return;
    setNewEmailError('');
    try {
      await addEmailMutation.mutateAsync({
        personId: editData.id,
        data: { email: newEmail.trim() },
      });
      setNewEmail('');
    } catch {
      setNewEmailError('Ongeldig of bestaand e-mailadres');
    }
  };

  const handleRemoveEmail = async (emailId: string) => {
    if (!editData) return;
    await removeEmailMutation.mutateAsync({ personId: editData.id, emailId });
  };

  const handleSetDefaultEmail = async (emailId: string) => {
    if (!editData) return;
    await setDefaultEmailMutation.mutateAsync({ personId: editData.id, emailId });
  };

  // Phone management handlers
  const handleAddPhone = async () => {
    if (!editData || !newPhone.trim()) return;
    setNewPhoneError('');
    try {
      await addPhoneMutation.mutateAsync({
        personId: editData.id,
        data: { phone_number: newPhone.trim(), label: newPhoneLabel },
      });
      setNewPhone('');
      setNewPhoneLabel('werk');
    } catch {
      setNewPhoneError('Ongeldig of bestaand telefoonnummer');
    }
  };

  const handleRemovePhone = async (phoneId: string) => {
    if (!editData) return;
    await removePhoneMutation.mutateAsync({ personId: editData.id, phoneId });
  };

  const handleSetDefaultPhone = async (phoneId: string) => {
    if (!editData) return;
    await setDefaultPhoneMutation.mutateAsync({ personId: editData.id, phoneId });
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

  // When a one-time API key is displayed, prevent accidental close.
  const isShowingKey = !!displayApiKey;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      closeable={!isShowingKey}
      footer={
        isShowingKey ? (
          <Button onClick={onClose}>
            Ik heb de sleutel gekopieerd
          </Button>
        ) : (
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
        )
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

        {/* Email field — create mode (non-agent): single input; edit mode: managed list */}
        {!isAgent && isCreateMode && selectedPerson && (
          <Input
            label="E-mail"
            type="email"
            value={email || 'Geen e-mail'}
            onChange={() => {}}
            disabled
          />
        )}
        {!isAgent && isCreateMode && !selectedPerson && (
          <Input
            label="E-mail"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => setEmailTouched(true)}
            placeholder="email@voorbeeld.nl"
            required
            error={emailTouched && !email.trim() ? 'E-mail is verplicht' : undefined}
          />
        )}

        {/* Email management — edit mode, non-agent */}
        {!isAgent && isEditMode && (
          <div>
            <label className="block text-sm font-medium text-text mb-1">E-mailadressen</label>
            {personEmails.length === 0 ? (
              <p className="text-sm text-text-secondary italic">Geen e-mailadressen</p>
            ) : (
              <ul className="space-y-1 mb-2">
                {personEmails.map((em) => (
                  <li key={em.id} className="group flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm">
                    <Mail className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                    <span className="flex-1 truncate">{em.email}</span>
                    <button
                      type="button"
                      onClick={() => handleSetDefaultEmail(em.id)}
                      className="shrink-0 p-0.5 rounded hover:bg-gray-100 transition-colors"
                      title={em.is_default ? 'Standaard e-mail' : 'Instellen als standaard'}
                    >
                      <Star className={`h-3.5 w-3.5 ${em.is_default ? 'fill-amber-400 text-amber-400' : 'text-gray-300 group-hover:text-gray-400'}`} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemoveEmail(em.id)}
                      className="shrink-0 p-0.5 rounded hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                      title="Verwijderen"
                    >
                      <X className="h-3.5 w-3.5 text-red-400 hover:text-red-600" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex items-center gap-2">
              <input
                type="email"
                value={newEmail}
                onChange={(e) => { setNewEmail(e.target.value); setNewEmailError(''); }}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddEmail(); } }}
                placeholder="Nieuw e-mailadres..."
                className="flex-1 rounded-lg border border-border px-3 py-1.5 text-sm text-text placeholder:text-text-secondary/50 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              />
              <button
                type="button"
                onClick={handleAddEmail}
                disabled={!newEmail.trim() || addEmailMutation.isPending}
                className="flex items-center justify-center h-8 w-8 rounded-lg border border-border hover:bg-gray-50 transition-colors disabled:opacity-40"
                title="Toevoegen"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
            {newEmailError && (
              <p className="mt-1 text-xs text-red-600">{newEmailError}</p>
            )}
          </div>
        )}

        {/* Phone management — edit mode, non-agent */}
        {!isAgent && isEditMode && (
          <div>
            <label className="block text-sm font-medium text-text mb-1">Telefoonnummers</label>
            {personPhones.length === 0 ? (
              <p className="text-sm text-text-secondary italic">Geen telefoonnummers</p>
            ) : (
              <ul className="space-y-1 mb-2">
                {personPhones.map((ph) => (
                  <li key={ph.id} className="group flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm">
                    <Phone className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                    <span className="flex-1 truncate">{ph.phone_number}</span>
                    <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-text-secondary">
                      {PHONE_LABELS[ph.label] ?? ph.label}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleSetDefaultPhone(ph.id)}
                      className="shrink-0 p-0.5 rounded hover:bg-gray-100 transition-colors"
                      title={ph.is_default ? 'Standaard telefoonnummer' : 'Instellen als standaard'}
                    >
                      <Star className={`h-3.5 w-3.5 ${ph.is_default ? 'fill-amber-400 text-amber-400' : 'text-gray-300 group-hover:text-gray-400'}`} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemovePhone(ph.id)}
                      className="shrink-0 p-0.5 rounded hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                      title="Verwijderen"
                    >
                      <X className="h-3.5 w-3.5 text-red-400 hover:text-red-600" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex items-center gap-2">
              <input
                type="tel"
                value={newPhone}
                onChange={(e) => { setNewPhone(e.target.value); setNewPhoneError(''); }}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddPhone(); } }}
                placeholder="+31 6 12345678"
                className="flex-1 rounded-lg border border-border px-3 py-1.5 text-sm text-text placeholder:text-text-secondary/50 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              />
              <select
                value={newPhoneLabel}
                onChange={(e) => setNewPhoneLabel(e.target.value)}
                className="rounded-lg border border-border px-2 py-1.5 text-sm text-text bg-white focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
                {Object.entries(PHONE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleAddPhone}
                disabled={!newPhone.trim() || addPhoneMutation.isPending}
                className="flex items-center justify-center h-8 w-8 rounded-lg border border-border hover:bg-gray-50 transition-colors disabled:opacity-40"
                title="Toevoegen"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
            {newPhoneError && (
              <p className="mt-1 text-xs text-red-600">{newPhoneError}</p>
            )}
          </div>
        )}

        {isAgent && (
          <>
            <div>
              <label className="block text-sm font-medium text-text mb-1">API Key</label>
              {displayApiKey ? (
                <>
                  <div className="flex items-center gap-2">
                    <input
                      type={showKey ? 'text' : 'password'}
                      readOnly
                      value={displayApiKey}
                      className="flex-1 rounded-lg border border-border bg-gray-50 px-3 py-2 text-sm font-mono text-text-secondary"
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey(!showKey)}
                      className="flex items-center justify-center h-9 w-9 rounded-lg border border-border hover:bg-gray-50 transition-colors"
                      title={showKey ? 'Verberg API key' : 'Toon API key'}
                    >
                      {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      type="button"
                      onClick={handleCopyKey}
                      className="flex items-center justify-center h-9 w-9 rounded-lg border border-border hover:bg-gray-50 transition-colors"
                      title="Kopieer API key"
                    >
                      {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  <p className="mt-1 text-xs text-amber-600 font-medium">
                    Deze sleutel wordt slechts eenmaal getoond. Kopieer en bewaar deze veilig.
                  </p>
                </>
              ) : editData ? (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={editData.has_api_key ? '••••••••••••••••••••••••••' : 'Geen API key'}
                    className="flex-1 rounded-lg border border-border bg-gray-50 px-3 py-2 text-sm font-mono text-text-secondary/50"
                  />
                  {confirmRotate ? (
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={handleRotateKey}
                        disabled={rotateApiKeyMutation.isPending}
                        className="flex items-center justify-center h-9 px-3 rounded-lg border border-red-300 bg-red-50 hover:bg-red-100 transition-colors text-sm gap-1.5 text-red-700 disabled:opacity-50"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${rotateApiKeyMutation.isPending ? 'animate-spin' : ''}`} />
                        Bevestig
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmRotate(false)}
                        className="flex items-center justify-center h-9 px-3 rounded-lg border border-border hover:bg-gray-50 transition-colors text-sm"
                      >
                        Annuleer
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={handleRotateKey}
                      className="flex items-center justify-center h-9 px-3 rounded-lg border border-border hover:bg-gray-50 transition-colors text-sm gap-1.5"
                      title="Genereer nieuwe API key (de oude wordt ongeldig)"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Roteer
                    </button>
                  )}
                </div>
              ) : (
                <p className="text-sm text-text-secondary">
                  API key wordt automatisch gegenereerd na aanmaken.
                </p>
              )}
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
        {!editData && orgEenheidId && !isAgent && (
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
