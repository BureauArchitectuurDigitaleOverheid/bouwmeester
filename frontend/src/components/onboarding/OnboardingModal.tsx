import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost, apiGet, ApiError } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { Modal } from '@/components/common/Modal';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { FUNCTIE_LABELS } from '@/types';
import type { Person } from '@/types';

const DEFAULT_FUNCTIE_OPTIONS: SelectOption[] = Object.entries(FUNCTIE_LABELS).map(
  ([value, label]) => ({ value, label }),
);

interface OnboardingPayload {
  naam: string;
  functie: string;
  organisatie_eenheid_id?: string;
  merge_with_id?: string;
}

export function OnboardingModal() {
  const { person, refreshAuthStatus } = useAuth();
  const queryClient = useQueryClient();

  const [naam, setNaam] = useState(person?.name ?? '');
  const [functie, setFunctie] = useState('');
  const [functieOptions, setFunctieOptions] = useState<SelectOption[]>(DEFAULT_FUNCTIE_OPTIONS);
  const [orgId, setOrgId] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Merge candidate state
  const [mergeCandidates, setMergeCandidates] = useState<Person[]>([]);
  const [mergeWithId, setMergeWithId] = useState<string | null>(null);
  const [mergeChecked, setMergeChecked] = useState(false);

  // Fetch merge candidates on mount
  useEffect(() => {
    let cancelled = false;
    apiGet<Person[]>('/api/auth/merge-candidates')
      .then((candidates) => {
        if (!cancelled) {
          setMergeCandidates(candidates);
          setMergeChecked(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMergeChecked(true);
        }
      });
    return () => { cancelled = true; };
  }, []);

  const mutation = useMutation({
    mutationFn: (data: OnboardingPayload) =>
      apiPost('/api/auth/onboarding', data),
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

  const canSubmit = mergeWithId
    ? true
    : naam.trim().length > 0 && functie.trim().length > 0 && orgId.length > 0;

  const handleSubmit = () => {
    if (!canSubmit) return;
    setError(null);
    if (mergeWithId) {
      // Merge mode: only merge_with_id is needed; org is not required
      mutation.mutate({
        naam: naam.trim() || person?.name || '',
        functie: functie.trim() || 'medewerker',
        merge_with_id: mergeWithId,
      });
    } else {
      mutation.mutate({
        naam: naam.trim(),
        functie: functie.trim(),
        organisatie_eenheid_id: orgId,
      });
    }
  };

  // Show merge candidates if found
  const showMergePrompt = mergeChecked && mergeCandidates.length > 0 && !mergeWithId;

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
          {mutation.isPending ? 'Bezig...' : mergeWithId ? 'Samenvoegen' : 'Profiel voltooien'}
        </button>
      }
    >
      {showMergePrompt && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm font-medium text-blue-800 mb-2">
            We vonden een bestaand account dat bij jou lijkt te horen:
          </p>
          <div className="space-y-2">
            {mergeCandidates.map((c) => (
              <div key={c.id} className="flex items-center justify-between bg-white p-2 rounded border border-blue-100">
                <div>
                  <p className="text-sm font-medium text-text">{c.naam}</p>
                  <p className="text-xs text-text-secondary">
                    {c.default_email || c.email}
                    {c.functie && ` \u2014 ${c.functie}`}
                  </p>
                </div>
                <button
                  onClick={() => setMergeWithId(c.id)}
                  className="px-3 py-1 text-xs font-medium rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors"
                >
                  Dit ben ik
                </button>
              </div>
            ))}
          </div>
          <button
            onClick={() => { setMergeCandidates([]); }}
            className="mt-2 text-xs text-blue-600 hover:text-blue-800 transition-colors"
          >
            Ik ben nieuw &mdash; verder zonder samenvoegen
          </button>
        </div>
      )}

      {mergeWithId && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800">
            Je account wordt samengevoegd met het bestaande profiel. Klik &quot;Samenvoegen&quot; om door te gaan.
          </p>
          <button
            onClick={() => setMergeWithId(null)}
            className="mt-1 text-xs text-green-600 hover:text-green-800 transition-colors"
          >
            Annuleren
          </button>
        </div>
      )}

      {!mergeWithId && (
        <>
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

            {error && <p className="text-sm text-red-600">{error}</p>}
          </div>
        </>
      )}

      {mergeWithId && error && <p className="text-sm text-red-600 mt-2">{error}</p>}
    </Modal>
  );
}
