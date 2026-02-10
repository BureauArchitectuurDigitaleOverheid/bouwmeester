import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost, ApiError } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { Modal } from '@/components/common/Modal';
import { CascadingOrgSelect } from '@/components/common/CascadingOrgSelect';

interface OnboardingPayload {
  naam: string;
  functie: string;
  organisatie_eenheid_id: string;
}

export function OnboardingModal() {
  const { person, refreshAuthStatus } = useAuth();
  const queryClient = useQueryClient();

  const [naam, setNaam] = useState(person?.name ?? '');
  const [functie, setFunctie] = useState('');
  const [orgId, setOrgId] = useState('');
  const [error, setError] = useState<string | null>(null);

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

        <div>
          <label className="block text-sm font-medium text-text mb-1">Functie</label>
          <input
            type="text"
            value={functie}
            onChange={(e) => setFunctie(e.target.value)}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
            placeholder="bijv. Beleidsmedewerker, Directeur"
          />
        </div>

        <CascadingOrgSelect value={orgId} onChange={setOrgId} />

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </Modal>
  );
}
