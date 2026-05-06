import { useState, useCallback, useMemo } from 'react';

import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';
import {
  usePeople,
  useCreatePerson,
  useExpertiseValues,
  useAddPersonOrganisatie,
} from '@/hooks/usePeople';
import { useAddLeadContact } from '@/hooks/useLeads';
import {
  useSamenwerkingsverbanden,
  useAddLid,
} from '@/hooks/useSamenwerkingsverbanden';
import {
  LEAD_CONTACT_ROL_LABELS,
  SAMENWERKINGSVERBAND_TYPE_LABELS,
} from '@/types';

const CONTACT_ROLLEN: SelectOption[] = Object.entries(LEAD_CONTACT_ROL_LABELS).map(
  ([value, label]) => ({ value, label }),
);

interface Props {
  leadId: string | null;
  onClose: () => void;
}

type Mode = 'select' | 'create';

export function AddLeadContactModal({ leadId, onClose }: Props) {
  const { data: people = [] } = usePeople();
  const { data: expertiseValues = [] } = useExpertiseValues();
  const { data: samenwerkingsverbanden = [] } = useSamenwerkingsverbanden({ actief: true });
  const createPerson = useCreatePerson();
  const addContact = useAddLeadContact();
  const addPersonOrg = useAddPersonOrganisatie();
  const addLidMutation = useAddLid();

  const [mode, setMode] = useState<Mode>('select');
  const [personId, setPersonId] = useState('');
  const [rol, setRol] = useState('contactpersoon');

  // Velden voor "create"-mode
  const [naam, setNaam] = useState('');
  const [email, setEmail] = useState('');
  const [functie, setFunctie] = useState('');
  const [expertise, setExpertise] = useState('');
  const [orgEenheidId, setOrgEenheidId] = useState('');
  const [swvIds, setSwvIds] = useState<Set<string>>(new Set());
  const [expertiseLocalAdded, setExpertiseLocalAdded] = useState<string[]>([]);

  const personOptions: SelectOption[] = people.map((p) => {
    const parts = [p.functie, p.expertise].filter((v): v is string => !!v);
    return {
      value: p.id,
      label: p.naam,
      description: parts.length > 0 ? parts.join(' · ') : undefined,
    };
  });

  const expertiseOptions: SelectOption[] = useMemo(
    () => [
      ...expertiseValues.map((v) => ({ value: v, label: v })),
      ...expertiseLocalAdded
        .filter((v) => !expertiseValues.includes(v))
        .map((v) => ({ value: v, label: v })),
    ],
    [expertiseValues, expertiseLocalAdded],
  );

  const toggleSwv = (id: string) => {
    setSwvIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const switchToCreate = useCallback((typedName: string) => {
    setMode('create');
    setNaam(typedName);
    setEmail('');
    setFunctie('');
    setExpertise('');
    setOrgEenheidId('');
    setSwvIds(new Set());
    return null;
  }, []);

  const resetAndClose = useCallback(() => {
    setMode('select');
    setPersonId('');
    setRol('contactpersoon');
    setNaam('');
    setEmail('');
    setFunctie('');
    setExpertise('');
    setOrgEenheidId('');
    setSwvIds(new Set());
    setExpertiseLocalAdded([]);
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
    if (!leadId || !naam.trim()) return;

    let created;
    try {
      created = await createPerson.mutateAsync({
        naam: naam.trim(),
        email: email.trim() || undefined,
        functie: functie.trim() || undefined,
        expertise: expertise.trim() || undefined,
        force: true,
      });
    } catch {
      return; // toast getoond, modal blijft open
    }
    const newPersonId = created.id;

    // Best-effort follow-ups; falen blokkeert de lead-koppeling niet.
    const today = new Date().toISOString().slice(0, 10);
    if (orgEenheidId) {
      try {
        await addPersonOrg.mutateAsync({
          personId: newPersonId,
          data: { organisatie_eenheid_id: orgEenheidId, start_datum: today },
        });
      } catch {
        // ignore — toast getoond
      }
    }
    for (const swvId of swvIds) {
      try {
        await addLidMutation.mutateAsync({
          swvId,
          data: { person_id: newPersonId, start_datum: today },
        });
      } catch {
        // ignore
      }
    }

    try {
      await addContact.mutateAsync({ leadId, personId: newPersonId, rol });
      resetAndClose();
    } catch {
      // toast
    }
  }, [
    leadId,
    naam,
    email,
    functie,
    expertise,
    orgEenheidId,
    swvIds,
    rol,
    createPerson,
    addPersonOrg,
    addLidMutation,
    addContact,
    resetAndClose,
  ]);

  const isPending =
    createPerson.isPending || addContact.isPending || addPersonOrg.isPending || addLidMutation.isPending;

  return (
    <Modal
      open={!!leadId}
      onClose={resetAndClose}
      title={
        mode === 'create' ? 'Nieuwe contactpersoon' : 'Externe contactpersoon toevoegen'
      }
      size={mode === 'create' ? 'md' : 'sm'}
      zIndex={60}
      footer={
        mode === 'create' ? (
          <>
            <Button variant="secondary" onClick={() => setMode('select')}>
              Terug
            </Button>
            <Button
              onClick={handleSubmitCreate}
              loading={isPending}
              disabled={!naam.trim()}
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
            options={CONTACT_ROLLEN}
            placeholder="Selecteer een rol..."
            searchable={false}
          />
        </div>
      ) : (
        <div className="space-y-4">
          <Input
            label="Naam"
            value={naam}
            onChange={(e) => setNaam(e.target.value)}
            required
            autoFocus
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="E-mail"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@voorbeeld.nl"
            />
            <Input
              label="Functie"
              value={functie}
              onChange={(e) => setFunctie(e.target.value)}
              placeholder="bv. wetgevingsjurist"
            />
          </div>
          <CreatableSelect
            label="Expertise"
            value={expertise}
            onChange={setExpertise}
            options={expertiseOptions}
            placeholder="Bijv. wetgevingsjurist, BIT-adviseur..."
            onCreate={async (text) => {
              const value = text.trim();
              if (!value) return null;
              setExpertiseLocalAdded((prev) =>
                prev.includes(value) ? prev : [...prev, value],
              );
              setExpertise(value);
              return value;
            }}
            createLabel="Nieuwe expertise toevoegen"
          />
          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Organisatie-eenheid (optioneel)
            </label>
            <CascadingOrgSelect
              value={orgEenheidId}
              onChange={setOrgEenheidId}
            />
          </div>
          {samenwerkingsverbanden.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-text mb-1">
                Samenwerkingsverbanden (optioneel)
              </label>
              <div className="max-h-32 overflow-y-auto rounded-lg border border-border p-2 space-y-1">
                {samenwerkingsverbanden.map((s) => (
                  <label
                    key={s.id}
                    className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 rounded px-1 py-0.5"
                  >
                    <input
                      type="checkbox"
                      checked={swvIds.has(s.id)}
                      onChange={() => toggleSwv(s.id)}
                      className="rounded border-border"
                    />
                    <span className="flex-1 truncate">{s.naam}</span>
                    <span className="text-xs text-text-secondary shrink-0">
                      {SAMENWERKINGSVERBAND_TYPE_LABELS[s.type] ?? s.type}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
          <CreatableSelect
            label="Rol op deze lead"
            value={rol}
            onChange={setRol}
            options={CONTACT_ROLLEN}
            placeholder="Selecteer een rol..."
            searchable={false}
          />
        </div>
      )}
    </Modal>
  );
}
