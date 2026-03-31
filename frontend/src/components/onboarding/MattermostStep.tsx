import { useEffect } from 'react';
import { MattermostLinkSection } from '@/components/settings/MattermostLinkSection';
import { useMattermostLinkStatus } from '@/hooks/useMattermost';
import { useAuth } from '@/contexts/AuthContext';
import { MessageSquare } from 'lucide-react';

export function MattermostStep({ onComplete }: { onComplete: () => void }) {
  const { person: authPerson } = useAuth();
  const personId = authPerson?.id ?? undefined;
  const hasPersonId = !!personId;

  // Poll link status to detect when linking completes.
  const { data: linkStatus } = useMattermostLinkStatus(true, hasPersonId, personId);

  useEffect(() => {
    if (linkStatus?.linked) {
      // Brief delay so user sees the success state before advancing.
      const timer = setTimeout(() => onComplete(), 1500);
      return () => clearTimeout(timer);
    }
  }, [linkStatus?.linked, onComplete]);

  return (
    <div>
      <div className="flex items-start gap-3 mb-4">
        <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-blue-100 shrink-0">
          <MessageSquare className="h-5 w-5 text-blue-700" />
        </div>
        <div>
          <p className="text-sm text-text-secondary">
            Koppel je Mattermost-account om notificaties over taken en dossiers
            direct in Mattermost te ontvangen. Je kunt dit ook later doen via
            Instellingen.
          </p>
        </div>
      </div>

      <MattermostLinkSection />
    </div>
  );
}
