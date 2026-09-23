import type { InitiatiefDetail } from '@/types';
import { MattermostChannelsSection } from '@/components/mattermost/MattermostChannelsSection';
import { AbonnementenSection } from '@/components/parlementair/AbonnementenSection';

/**
 * The "Signalen" tab: what comes in from outside. The channels come first
 * because the parliamentary alerts and the proposed leads are delivered to
 * exactly those channels; apart, neither section explains the other.
 */
export function InitiatiefSignalen({ initiatief }: { initiatief: InitiatiefDetail }) {
  return (
    <nldd-container gap="32">
      <MattermostChannelsSection scope={{ type: 'initiatief', id: initiatief.id }} />
      <AbonnementenSection initiatiefId={initiatief.id} />
    </nldd-container>
  );
}
