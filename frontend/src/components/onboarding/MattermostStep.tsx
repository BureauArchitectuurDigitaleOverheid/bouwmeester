import { useEffect } from 'react';
import { MattermostLinkSection } from '@/components/settings/MattermostLinkSection';
import { useMattermostLinkStatus } from '@/hooks/useMattermost';
import { useAuth } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';

export function MattermostStep({ onComplete }: { onComplete: () => void }) {
  const { person: authPerson } = useAuth();
  const { currentPerson } = useCurrentPerson();
  const personId = authPerson?.id ?? currentPerson?.id ?? undefined;
  const hasPersonId = !!personId;

  const { data: linkStatus } = useMattermostLinkStatus(true, hasPersonId, personId);

  useEffect(() => {
    if (linkStatus?.linked) {
      const timer = setTimeout(() => onComplete(), 1500);
      return () => clearTimeout(timer);
    }
  }, [linkStatus?.linked, onComplete]);

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
