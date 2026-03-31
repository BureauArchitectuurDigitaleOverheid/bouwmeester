import { useEffect } from 'react';
import { MattermostLinkSection } from '@/components/settings/MattermostLinkSection';
import { useMattermostLinkStatus } from '@/hooks/useMattermost';
import { useAuth } from '@/contexts/AuthContext';
import { Check } from 'lucide-react';

export function MattermostStep({ onComplete }: { onComplete: () => void }) {
  const { person: authPerson } = useAuth();
  const personId = authPerson?.id ?? undefined;
  const hasPersonId = !!personId;

  const { data: linkStatus } = useMattermostLinkStatus(true, hasPersonId, personId);
  const linked = linkStatus?.linked ?? false;

  // Auto-advance after a short delay so the user sees the success state.
  useEffect(() => {
    if (linked) {
      const timer = setTimeout(() => onComplete(), 3000);
      return () => clearTimeout(timer);
    }
  }, [linked, onComplete]);

  if (linked) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <div className="flex items-center justify-center h-12 w-12 rounded-full bg-green-100 mb-3">
          <Check className="h-6 w-6 text-green-600" />
        </div>
        <h3 className="text-base font-semibold text-text mb-1">Mattermost gekoppeld</h3>
        <p className="text-sm text-text-secondary mb-4">
          Je ontvangt nu notificaties in Mattermost.
        </p>
        <button
          onClick={onComplete}
          className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 transition-colors"
        >
          Doorgaan
        </button>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-base font-semibold text-text mb-1">Koppel Mattermost</h3>
      <p className="text-sm text-text-secondary mb-4">
        Koppel je Mattermost-account om notificaties over taken en dossiers
        direct te ontvangen. Je kunt dit ook later doen via Instellingen.
      </p>
      <MattermostLinkSection compact />
    </div>
  );
}
