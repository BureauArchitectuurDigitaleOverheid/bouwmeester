import { MattermostLinkSection } from '@/components/settings/MattermostLinkSection';
import { VocabularySettings } from '@/components/settings/VocabularySettings';
import { WebAuthnSettings } from '@/components/settings/WebAuthnSettings';

export function InstellingenPage() {
  return (
    <nldd-container max-width="640px" horizontal-alignment="center" gap="24">
      <VocabularySettings />
      <WebAuthnSettings />
      <MattermostLinkSection />
    </nldd-container>
  );
}
