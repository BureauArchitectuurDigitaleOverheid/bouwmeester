import { useState } from 'react';
import { Sparkles, Loader2 } from 'lucide-react';
import { summarizeText } from '@/api/llm';

interface ContentSummaryProps {
  text: string;
  /** Minimum text length to show the summarize button */
  minLength?: number;
}

export function ContentSummary({ text, minLength = 500 }: ContentSummaryProps) {
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!text || text.length < minLength) return null;

  const handleSummarize = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await summarizeText(text);
      if (!res.available) {
        setError('Samenvatting niet beschikbaar (geen LLM-provider geconfigureerd).');
        return;
      }
      setSummary(res.summary);
    } catch {
      setError('Fout bij genereren van samenvatting.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-3">
      {!summary && (
        <button
          onClick={handleSummarize}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border text-text-secondary hover:text-text hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          Samenvatten
        </button>
      )}

      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}

      {summary && (
        <div className="mt-2 p-3 rounded-lg bg-primary-50/50 border border-primary-100">
          <p className="text-xs font-medium text-primary-700 mb-1">Samenvatting</p>
          <p className="text-sm text-text">{summary}</p>
          <button
            onClick={() => setSummary(null)}
            className="text-xs text-text-secondary hover:text-text mt-2 transition-colors"
          >
            Verbergen
          </button>
        </div>
      )}
    </div>
  );
}
