import { useState } from 'react';
import { AiActionButton } from '@/components/common/AiActionButton';
import { Icon } from '@/components/nldd/Icon';
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

      {error && <nldd-text size="xs" color="critical">{error}</nldd-text>}

      {result && (
        <div className="space-y-3">
          {/* Score */}
          <div className="flex items-center gap-2">
            <Icon
              name={result.completed_count === result.total_steps ? 'check-mark-circle' : 'exclamation-triangle'}
              size="md"
              className={result.completed_count === result.total_steps ? 'text-emerald-500' : 'text-amber-500'}
            />
            <span className="text-sm font-medium text-text">
              {result.completed_count}/{result.total_steps} stappen voltooid
            </span>
          </div>

          {/* Gap list */}
          {result.gaps.length > 0 && (
            <div className="space-y-1.5">
              {result.gaps.map((gap) => (
                <nldd-inline-dialog
                  key={gap.step_number}
                  variant="alert"
                  size="md"
                  horizontal-alignment="left"
                  text={`Stap ${gap.step_number}: ${gap.step_question}`}
                  supporting-text={`Ontbreekt: ${gap.missing_types.map((t) => NODE_TYPE_LABELS[t as NodeType] ?? t).join(', ')}`}
                />
              ))}
            </div>
          )}

          {/* LLM narrative */}
          {result.narrative && (
            <nldd-inline-dialog
              size="md"
              horizontal-alignment="left"
              icon="sparkles"
              icon-color="accent"
              text="AI-analyse"
              supporting-text={result.narrative}
            />
          )}

          {/* Recommendations */}
          {result.recommendations.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <Icon name="lightbulb" size="sm" className="text-amber-500" />
                <nldd-text size="xs" color="secondary" weight="medium">Aanbevelingen</nldd-text>
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
