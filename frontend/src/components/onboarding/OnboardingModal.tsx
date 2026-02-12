import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost, ApiError } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { Modal } from '@/components/common/Modal';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { addPersonEmail, addPersonPhone } from '@/api/people';
import { FUNCTIE_LABELS, PHONE_LABELS } from '@/types';
import type { Person } from '@/types';
import { Mail, Phone, Plus, X } from 'lucide-react';

const DEFAULT_FUNCTIE_OPTIONS: SelectOption[] = Object.entries(FUNCTIE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

const PHONE_LABEL_OPTIONS = Object.entries(PHONE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

interface OnboardingPayload {
  naam: string;
  functie: string;
  organisatie_eenheid_id: string;
}

interface ExtraEmail {
  email: string;
}

interface ExtraPhone {
  phone_number: string;
  label: string;
}

export function OnboardingModal() {
  const { person, refreshAuthStatus } = useAuth();
  const queryClient = useQueryClient();

  const [naam, setNaam] = useState(person?.name ?? '');
  const [functie, setFunctie] = useState('');
  const [functieOptions, setFunctieOptions] = useState<SelectOption[]>(DEFAULT_FUNCTIE_OPTIONS);
  const [orgId, setOrgId] = useState('');
  const [extraEmails, setExtraEmails] = useState<ExtraEmail[]>([]);
  const [extraPhones, setExtraPhones] = useState<ExtraPhone[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const mutation = useMutation({
    mutationFn: async (data: OnboardingPayload) => {
      const result = await apiPost<Person>('/api/auth/onboarding', data);
      // After onboarding succeeds, add any extra emails/phones
      const personId = result.id;
      const promises: Promise<unknown>[] = [];
      for (const e of extraEmails) {
        if (e.email.trim()) {
          promises.push(addPersonEmail(personId, { email: e.email.trim() }));
        }
      }
      for (const p of extraPhones) {
        if (p.phone_number.trim()) {
          promises.push(addPersonPhone(personId, { phone_number: p.phone_number.trim(), label: p.label }));
        }
      }
      const results = await Promise.allSettled(promises);
      const failed = results.filter((r) => r.status === 'rejected');
      if (failed.length > 0) {
        setWarnings(
          failed.map((r) => {
            const reason = (r as PromiseRejectedResult).reason;
            if (reason instanceof ApiError && reason.body && typeof reason.body === 'object' && 'detail' in reason.body) {
              return String((reason.body as { detail: string }).detail);
            }
            return 'Kon contactgegeven niet opslaan';
          }),
        );
      }
      return result;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['people'] });
      await refreshAuthStatus();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.body && typeof err.body === 'object' && 'detail' in err.body) {
        setError(String((err.body as { detail: string }).detail));
      } else {
        setError('Er is iets misgegaan. Probeer het opnieuw.');
      }
    },
  });

  const handleCreateFunctie = async (text: string): Promise<string | null> => {
    const value = text.toLowerCase().replace(/\s+/g, '_');
    setFunctieOptions((prev) => [...prev, { value, label: text }]);
    setFunctie(value);
    return value;
  };

  const canSubmit = naam.trim().length > 0 && functie.trim().length > 0 && orgId.length > 0;

  const handleSubmit = () => {
    if (!canSubmit) return;
    setError(null);
    mutation.mutate({
      naam: naam.trim(),
      functie: functie.trim(),
      organisatie_eenheid_id: orgId,
    });
  };

  return (
    <Modal
      open
      onClose={() => {}}
      title="Welkom bij Bouwmeester"
      closeable={false}
      footer={
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || mutation.isPending}
          className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {mutation.isPending ? 'Bezig...' : 'Profiel voltooien'}
        </button>
      }
    >
      <p className="text-sm text-text-secondary mb-4">
        Vul je profiel aan om aan de slag te gaan.
      </p>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-text mb-1">Naam</label>
          <input
            type="text"
            value={naam}
            onChange={(e) => setNaam(e.target.value)}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
            placeholder="Volledige naam"
          />
        </div>

        <CreatableSelect
          label="Functie"
          value={functie}
          onChange={setFunctie}
          options={functieOptions}
          placeholder="Selecteer of maak functie..."
          onCreate={handleCreateFunctie}
          createLabel="Nieuwe functie aanmaken"
        />

        <CascadingOrgSelect value={orgId} onChange={setOrgId} />

        {/* Extra email addresses */}
        <div>
          <label className="block text-sm font-medium text-text mb-1">
            Extra e-mailadressen
          </label>
          {person?.email && (
            <p className="text-xs text-text-secondary mb-2">
              {person.email} wordt automatisch toegevoegd.
            </p>
          )}
          {extraEmails.map((entry, i) => (
            <div key={i} className="flex items-center gap-2 mb-2">
              <Mail className="h-4 w-4 text-text-secondary shrink-0" />
              <input
                type="email"
                value={entry.email}
                onChange={(e) => {
                  const updated = [...extraEmails];
                  updated[i] = { email: e.target.value };
                  setExtraEmails(updated);
                }}
                className="flex-1 rounded-lg border border-border px-3 py-1.5 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                placeholder="E-mailadres"
              />
              <button
                type="button"
                onClick={() => setExtraEmails(extraEmails.filter((_, j) => j !== i))}
                className="text-text-secondary hover:text-red-600 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setExtraEmails([...extraEmails, { email: '' }])}
            className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 transition-colors"
          >
            <Plus className="h-3 w-3" />
            E-mailadres toevoegen
          </button>
        </div>

        {/* Phone numbers */}
        <div>
          <label className="block text-sm font-medium text-text mb-1">
            Telefoonnummers
          </label>
          {extraPhones.map((entry, i) => (
            <div key={i} className="flex items-center gap-2 mb-2">
              <Phone className="h-4 w-4 text-text-secondary shrink-0" />
              <input
                type="tel"
                value={entry.phone_number}
                onChange={(e) => {
                  const updated = [...extraPhones];
                  updated[i] = { ...updated[i], phone_number: e.target.value };
                  setExtraPhones(updated);
                }}
                className="flex-1 rounded-lg border border-border px-3 py-1.5 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                placeholder="Telefoonnummer"
              />
              <select
                value={entry.label}
                onChange={(e) => {
                  const updated = [...extraPhones];
                  updated[i] = { ...updated[i], label: e.target.value };
                  setExtraPhones(updated);
                }}
                className="rounded-lg border border-border px-2 py-1.5 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
                {PHONE_LABEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setExtraPhones(extraPhones.filter((_, j) => j !== i))}
                className="text-text-secondary hover:text-red-600 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setExtraPhones([...extraPhones, { phone_number: '', label: 'werk' }])}
            className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 transition-colors"
          >
            <Plus className="h-3 w-3" />
            Telefoonnummer toevoegen
          </button>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {warnings.length > 0 && (
          <div className="text-sm text-amber-600">
            {warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
