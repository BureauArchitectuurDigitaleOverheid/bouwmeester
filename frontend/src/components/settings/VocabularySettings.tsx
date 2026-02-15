import { BookOpen } from 'lucide-react';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { VOCABULARY_LABELS, type VocabularyId } from '@/vocabulary';

export function VocabularySettings() {
  const { vocabularyId, setVocabularyId } = useVocabulary();

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary-100">
          <BookOpen className="h-5 w-5 text-primary-700" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-text">Vocabulaire</h2>
          <p className="text-sm text-text-secondary">
            Kies de terminologie die je wilt gebruiken in de applicatie.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {(Object.keys(VOCABULARY_LABELS) as VocabularyId[]).map((id) => (
          <button
            key={id}
            onClick={() => setVocabularyId(id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              vocabularyId === id
                ? 'bg-primary-100 text-primary-700 border border-primary-200'
                : 'border border-border text-text-secondary hover:text-text hover:bg-gray-50'
            }`}
          >
            {VOCABULARY_LABELS[id]}
          </button>
        ))}
      </div>
    </div>
  );
}
