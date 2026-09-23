import type { InitiatiefDetail } from '@/types';
import { MattermostChannelsSection } from '@/components/mattermost/MattermostChannelsSection';
import { AbonnementenSection } from '@/components/parlementair/AbonnementenSection';
import { SignaalcontextSection } from '@/components/parlementair/SignaalcontextSection';

/**
 * De "Signalen"-tab: wat er van buiten binnenkomt.
 *
 * De volgorde volgt het proces: je volgt zoektermen, een oordeel bepaalt
 * wat daarvan de moeite waard is, en wat overblijft gaat naar een kanaal.
 * Eerder stonden de kanalen bovenaan, omdat de ene sectie de andere
 * uitlegt; het gevolg was dat je eerst las waar iets heen gaat en pas
 * daarna wat er heen gaat.
 *
 * De kanalenkaart houdt zijn eigen naam en zakt naar onderen. "Bezorging"
 * zou hier passend lijken, maar die kaart draagt ook de schakelaars voor
 * leads en voor berichten-als-notities, en die hebben met signalen niets
 * te maken. Een kop die twee derde van zijn inhoud niet dekt is
 * misleidender dan een saaie kop.
 */
export function InitiatiefSignalen({ initiatief }: { initiatief: InitiatiefDetail }) {
  return (
    <nldd-container gap="16">
      <AbonnementenSection initiatiefId={initiatief.id} />
      <SignaalcontextSection initiatiefId={initiatief.id} />
      <MattermostChannelsSection scope={{ type: 'initiatief', id: initiatief.id }} />
    </nldd-container>
  );
}
