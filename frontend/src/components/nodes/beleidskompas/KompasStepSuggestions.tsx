import { useState } from 'react';
import { Check, X, Loader2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { AiActionButton } from '@/components/common/AiActionButton';
import { suggestKompasLinks } from '@/api/llm';
import { apiPost } from '@/api/client';
import { Badge } from '@/components/common/Badge';
import { queryKeys } from '@/hooks/queryKeys';
import { NODE_TYPE_COLORS, type EdgeSuggestionItem, type NodeType } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

interface KompasStepSuggestionsProps {
  dossierId: string;
  stepNodeTypes: NodeType[];
  stepDescription: string;
}

export function KompasStepSuggestions({
  dossierId,
  stepNodeTypes,
  stepDescription,
}: KompasStepSuggestionsProps) {
  const queryClient = useQueryClient();
  const { nodeLabel } = useVocabulary();
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<EdgeSuggestionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const [approving, setApproving] = useState<Set<string>>(new Set());

  const handleSuggest = async () => {
    setLoading(true);
    setError(null);
    setSuggestions(null);
    setApproved(new Set());
    setRejected(new Set());
    try {
      const res = await suggestKompasLinks(dossierId, stepNodeTypes, stepDescription);
      if (!res.available) {
        setError('AI-suggesties zijn niet beschikbaar.');
        return;
      }
      setSuggestions(res.suggestions);
    } catch {
      setError('Fout bij ophalen van suggesties.');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (s: EdgeSuggestionItem) => {
    setApproving((prev) => new Set([...prev, s.target_node_id]));
    try {
      await apiPost('/api/edges', {
        from_node_id: s.target_node_id,
        to_node_id: dossierId,
        edge_type_id: 'onderdeel_van',
        description: s.reason,
      });
      setApproved((prev) => new Set([...prev, s.target_node_id]));
      // Invalidate graph queries to refresh Beleidskompas
      await queryClient.invalidateQueries({ queryKey: queryKeys.nodes.graph(dossierId, 1) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.nodes.neighbors(dossierId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.edges.all });
    } catch {
      setError('Fout bij aanmaken van relatie.');
    } finally {
      setApproving((prev) => {
        const next = new Set(prev);
        next.delete(s.target_node_id);
        return next;
      });
    }
  };

  return (
    <div className="space-y-2">
      <AiActionButton
        label="Aanbevolen koppelingen"
        loading={loading}
        onClick={handleSuggest}
        compact
      />

      {error && <p className="text-xs text-red-500">{error}</p>}

      {suggestions !== null && suggestions.length === 0 && (
        <p className="text-xs text-text-secondary">Geen suggesties gevonden.</p>
      )}

      {suggestions && suggestions.length > 0 && (
        <div className="space-y-1.5">
          {suggestions.map((s) => {
            const isApproved = approved.has(s.target_node_id);
            const isRejected = rejected.has(s.target_node_id);

            return (
              <div
                key={s.target_node_id}
                className={`flex items-center justify-between p-2 rounded-lg border text-xs ${
                  isApproved
                    ? 'border-green-200 bg-green-50/50'
                    : isRejected
                      ? 'border-gray-200 bg-gray-50/50 opacity-50'
                      : 'border-border bg-white'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <Badge
                    variant={NODE_TYPE_COLORS[s.target_node_type as NodeType]}
                    dot
                  >
                    {nodeLabel(s.target_node_type)}
                  </Badge>
                  <span className="text-text truncate">{s.target_node_title}</span>
                  <span className="text-text-secondary shrink-0">
                    {Math.round(s.confidence * 100)}%
                  </span>
                </div>
                <div className="flex items-center gap-0.5 shrink-0 ml-1.5">
                  {!isApproved && !isRejected && (
                    <>
                      <button
                        onClick={() => handleApprove(s)}
                        disabled={approving.has(s.target_node_id)}
                        className="p-1 rounded text-green-600 hover:bg-green-50 transition-colors disabled:opacity-50"
                        title="Koppelen"
                      >
                        {approving.has(s.target_node_id) ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Check className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <button
                        onClick={() =>
                          setRejected((prev) => new Set([...prev, s.target_node_id]))
                        }
                        className="p-1 rounded text-text-secondary hover:text-red-500 hover:bg-red-50 transition-colors"
                        title="Afwijzen"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                  {isApproved && (
                    <span className="text-green-600 font-medium">Gekoppeld</span>
                  )}
                  {isRejected && (
                    <span className="text-text-secondary">Afgewezen</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
