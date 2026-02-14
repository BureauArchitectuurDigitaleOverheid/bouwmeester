import { useState } from 'react';
import { Sparkles, Loader2, Check, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { suggestEdges, type EdgeSuggestionItem } from '@/api/llm';
import { Badge } from '@/components/common/Badge';
import { NODE_TYPE_COLORS } from '@/types';
import { apiPost } from '@/api/client';

interface EdgeSuggestionsProps {
  nodeId: string;
}

export function EdgeSuggestions({ nodeId }: EdgeSuggestionsProps) {
  const navigate = useNavigate();
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
      const res = await suggestEdges(nodeId);
      if (!res.available) {
        setError('Relatie-suggesties zijn niet beschikbaar (geen LLM-provider geconfigureerd).');
        return;
      }
      setSuggestions(res.suggestions);
    } catch {
      setError('Fout bij ophalen van relatie-suggesties.');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (suggestion: EdgeSuggestionItem) => {
    setApproving((prev) => new Set([...prev, suggestion.target_node_id]));
    try {
      await apiPost('/api/edges', {
        from_node_id: nodeId,
        to_node_id: suggestion.target_node_id,
        edge_type_id: suggestion.suggested_edge_type || 'verwijst_naar',
        description: suggestion.reason,
      });
      setApproved((prev) => new Set([...prev, suggestion.target_node_id]));
    } catch {
      setError('Fout bij aanmaken van relatie. Mogelijk bestaat deze al.');
    } finally {
      setApproving((prev) => {
        const next = new Set(prev);
        next.delete(suggestion.target_node_id);
        return next;
      });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text">Voorgestelde relaties</h3>
        <button
          onClick={handleSuggest}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border text-text-secondary hover:text-text hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          Relaties suggereren
        </button>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {suggestions !== null && suggestions.length === 0 && (
        <p className="text-xs text-text-secondary">Geen suggesties gevonden.</p>
      )}

      {suggestions && suggestions.length > 0 && (
        <div className="space-y-2">
          {suggestions.map((s) => {
            const isApproved = approved.has(s.target_node_id);
            const isRejected = rejected.has(s.target_node_id);

            return (
              <div
                key={s.target_node_id}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  isApproved ? 'border-green-200 bg-green-50/50' :
                  isRejected ? 'border-gray-200 bg-gray-50/50 opacity-50' :
                  'border-border bg-white'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <Badge variant={NODE_TYPE_COLORS[s.target_node_type as keyof typeof NODE_TYPE_COLORS]} dot>
                    {s.target_node_type}
                  </Badge>
                  <button
                    onClick={() => navigate(`/nodes/${s.target_node_id}`)}
                    className="text-sm text-text hover:text-primary-700 truncate text-left transition-colors"
                  >
                    {s.target_node_title}
                  </button>
                  <span className="text-xs text-text-secondary shrink-0">
                    {Math.round(s.confidence * 100)}%
                  </span>
                </div>
                <div className="flex items-center gap-1 shrink-0 ml-2">
                  {!isApproved && !isRejected && (
                    <>
                      <button
                        onClick={() => handleApprove(s)}
                        disabled={approving.has(s.target_node_id)}
                        className="p-1.5 rounded-lg text-green-600 hover:bg-green-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Goedkeuren"
                      >
                        {approving.has(s.target_node_id) ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Check className="h-4 w-4" />
                        )}
                      </button>
                      <button
                        onClick={() => setRejected((prev) => new Set([...prev, s.target_node_id]))}
                        disabled={approving.has(s.target_node_id)}
                        className="p-1.5 rounded-lg text-text-secondary hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Afwijzen"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </>
                  )}
                  {isApproved && (
                    <span className="text-xs text-green-600 font-medium">Goedgekeurd</span>
                  )}
                  {isRejected && (
                    <span className="text-xs text-text-secondary font-medium">Afgewezen</span>
                  )}
                </div>
              </div>
            );
          })}
          {suggestions.length > 0 && (
            <p className="text-xs text-text-secondary mt-1">
              {suggestions[0].reason && `Reden: ${suggestions[0].reason}`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
