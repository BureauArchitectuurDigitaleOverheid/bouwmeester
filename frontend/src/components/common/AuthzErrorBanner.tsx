import { NlddButton } from '@/components/nldd/NlddButton';
import { useAuthzFailures } from '@/hooks/useCan';

/**
 * Shown while some of the rights on screen could not be fetched. The
 * affected main buttons stay visible but disabled (`useCan().showAction`);
 * this is where the user asks again.
 */
export function AuthzErrorBanner() {
  const { failed, retry } = useAuthzFailures();
  if (!failed) return null;
  return (
    <nldd-banner variant="warning" size="sm" text="Je rechten konden niet worden opgehaald. Sommige knoppen zijn tijdelijk uitgeschakeld.">
      <div slot="actions">
        <NlddButton text="Opnieuw proberen" variant="inherit-tinted" size="sm" onClick={retry} />
      </div>
    </nldd-banner>
  );
}
