import { useState } from 'react';
import { Sparkles, Loader2, Check, Plus, X } from 'lucide-react';
import { suggestTags, type TagSuggestionResponse } from '@/api/llm';

interface TagSuggestionsProps {
  title: string;
  description?: string;
  nodeType: string;
  /** Tags already on the node — these are filtered from matched suggestions */
  existingTagNames?: string[];
  onAcceptTag: (tagName: string, isNew: boolean) => void;
}

export function TagSuggestions({
  title,
  description,
  nodeType,
  existingTagNames = [],
  onAcceptTag,
}: TagSuggestionsProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TagSuggestionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acceptedTags, setAcceptedTags] = useState<Set<string>>(new Set());

  const handleSuggest = async () => {
    if (!title.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setAcceptedTags(new Set());
    try {
      const res = await suggestTags({
        title: title.trim(),
        description: description?.trim() || undefined,
        node_type: nodeType,
      });
      if (!res.available) {
        setError('Tag-suggesties zijn niet beschikbaar (geen LLM-provider geconfigureerd).');
        return;
      }
      setResult(res);
    } catch {
      setError('Fout bij ophalen van tag-suggesties.');
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = (tagName: string, isNew: boolean) => {
    setAcceptedTags((prev) => new Set([...prev, tagName]));
    onAcceptTag(tagName, isNew);
  };

  const existingSet = new Set(existingTagNames.map((n) => n.toLowerCase()));
  const filteredMatched = result?.matched_tags.filter(
    (t) => !existingSet.has(t.toLowerCase()),
  ) ?? [];

  const hasResults = filteredMatched.length > 0 || (result?.suggested_new_tags.length ?? 0) > 0;

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={handleSuggest}
        disabled={loading || !title.trim()}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border text-text-secondary hover:text-text hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Sparkles className="h-3.5 w-3.5" />
        )}
        Tags suggereren
      </button>

      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}

      {result && !hasResults && (
        <p className="text-xs text-text-secondary">Geen suggesties gevonden.</p>
      )}

      {result && hasResults && (
        <div className="space-y-2">
          {filteredMatched.length > 0 && (
            <div>
              <p className="text-xs font-medium text-text-secondary mb-1">Bestaande tags</p>
              <div className="flex flex-wrap gap-1.5">
                {filteredMatched.map((tag) => (
                  <TagChip
                    key={tag}
                    name={tag}
                    accepted={acceptedTags.has(tag)}
                    onAccept={() => handleAccept(tag, false)}
                  />
                ))}
              </div>
            </div>
          )}

          {result.suggested_new_tags.length > 0 && (
            <div>
              <p className="text-xs font-medium text-text-secondary mb-1">Nieuwe tags</p>
              <div className="flex flex-wrap gap-1.5">
                {result.suggested_new_tags.map((tag) => (
                  <TagChip
                    key={tag}
                    name={tag}
                    isNew
                    accepted={acceptedTags.has(tag)}
                    onAccept={() => handleAccept(tag, true)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TagChip({
  name,
  isNew = false,
  accepted,
  onAccept,
}: {
  name: string;
  isNew?: boolean;
  accepted: boolean;
  onAccept: () => void;
}) {
  if (accepted) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-700 px-2.5 py-0.5 text-xs font-medium">
        <Check className="h-3 w-3" />
        {name}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={onAccept}
      className="inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-600 hover:bg-primary-50 hover:text-primary-700 px-2.5 py-0.5 text-xs font-medium transition-colors"
    >
      {isNew ? <Plus className="h-3 w-3" /> : <Check className="h-3 w-3" />}
      {name}
    </button>
  );
}
