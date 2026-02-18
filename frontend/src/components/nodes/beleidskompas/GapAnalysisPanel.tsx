import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Lightbulb, Sparkles } from 'lucide-react';
import { AiActionButton } from '@/components/common/AiActionButton';
import { analyzeGaps } from '@/api/llm';
import { NODE_TYPE_LABELS, type GapAnalysisResponse, type NodeType } from '@/types';

interface GapAnalysisPanelProps {
  dossierId: string;
}

export function GapAnalysisPanel({ dossierId }: GapAnalysisPanelProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GapAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await analyzeGaps(dossierId);
      setResult(res);
    } catch {
      setError('Fout bij uitvoeren van de analyse.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text">Voltooiheidsanalyse</h3>
        <AiActionButton
          label="Analyse voltooiheid"
          loading={loading}
          onClick={handleAnalyze}
        />
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {result && (
        <div className="space-y-3">
          {/* Score */}
          <div className="flex items-center gap-2">
            {result.completed_count === result.total_steps ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-500" />
            )}
            <span className="text-sm font-medium text-text">
              {result.completed_count}/{result.total_steps} stappen voltooid
            </span>
          </div>

          {/* Gap list */}
          {result.gaps.length > 0 && (
            <div className="space-y-1.5">
              {result.gaps.map((gap) => (
                <div
                  key={gap.step_number}
                  className="flex items-start gap-2 p-2 rounded-lg bg-amber-50 border border-amber-200"
                >
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-amber-800">
                      Stap {gap.step_number}: {gap.step_question}
                    </p>
                    <p className="text-xs text-amber-700">
                      Ontbreekt:{' '}
                      {gap.missing_types
                        .map((t) => NODE_TYPE_LABELS[t as NodeType] ?? t)
                        .join(', ')}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* LLM narrative */}
          {result.narrative && (
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Sparkles className="h-3.5 w-3.5 text-slate-500" />
                <span className="text-xs font-medium text-slate-600">AI-analyse</span>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed">{result.narrative}</p>
            </div>
          )}

          {/* Recommendations */}
          {result.recommendations.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
                <span className="text-xs font-medium text-text-secondary">Aanbevelingen</span>
              </div>
              <ul className="space-y-1 ml-5">
                {result.recommendations.map((rec, i) => (
                  <li key={i} className="text-xs text-text-secondary list-disc">
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
