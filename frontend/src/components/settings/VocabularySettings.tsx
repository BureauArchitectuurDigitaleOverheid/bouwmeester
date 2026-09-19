import { useVocabulary } from '@/contexts/VocabularyContext';
import { VOCABULARY_LABELS, type VocabularyId } from '@/vocabulary';
import { NlddButton } from '@/components/nldd/NlddLink';
import { Icon } from '@/components/nldd/Icon';

export function VocabularySettings() {
  const { vocabularyId, setVocabularyId } = useVocabulary();

  return (
    <nldd-card>
      <nldd-container padding="24" gap="16">
        <nldd-container layout="row" gap="12" vertical-alignment="center">
          <Icon name="book" size="lg" />
          <nldd-container gap="2">
            <nldd-text weight="medium">Vocabulaire</nldd-text>
            <nldd-text size="sm" color="secondary">
              Kies de terminologie die je wilt gebruiken in de applicatie.
            </nldd-text>
          </nldd-container>
        </nldd-container>

        <nldd-container layout="row" gap="8">
          {(Object.keys(VOCABULARY_LABELS) as VocabularyId[]).map((id) => (
            <NlddButton
              key={id}
              text={VOCABULARY_LABELS[id]}
              variant={vocabularyId === id ? 'accent-transparent' : 'secondary'}
              onClick={() => setVocabularyId(id)}
            />
          ))}
        </nldd-container>
      </nldd-container>
    </nldd-card>
  );
}
