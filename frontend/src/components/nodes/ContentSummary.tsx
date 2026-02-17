import { useState } from 'react';
import { AiActionButton } from '@/components/common/AiActionButton';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
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
        <AiActionButton
          label="Samenvatten"
          loading={loading}
          onClick={handleSummarize}
        />
      )}

      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}

      {summary && (
        <div className="mt-2 p-3 rounded-lg bg-primary-50/50 border border-primary-100">
          <p className="text-xs font-medium text-primary-700 mb-1">Samenvatting</p>
          <div className="text-sm text-text">
            <MarkdownRenderer content={summary} />
          </div>
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
