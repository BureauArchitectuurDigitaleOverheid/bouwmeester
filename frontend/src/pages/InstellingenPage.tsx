import { MattermostLinkSection } from '@/components/settings/MattermostLinkSection';
import { VocabularySettings } from '@/components/settings/VocabularySettings';
import { WebAuthnSettings } from '@/components/settings/WebAuthnSettings';

export function InstellingenPage() {
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <VocabularySettings />
      <WebAuthnSettings />
      <MattermostLinkSection />
    </div>
  );
}
