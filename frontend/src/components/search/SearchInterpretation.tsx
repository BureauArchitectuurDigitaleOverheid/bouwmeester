import { X, Sparkles } from 'lucide-react';
import { NODE_TYPE_LABELS, type NodeType, type SearchInterpretation as Interpretation } from '@/types';

interface SearchInterpretationProps {
  interpretation: Interpretation;
  onRemoveNodeType: (type: string) => void;
  onRemoveTag: (tag: string) => void;
}

export function SearchInterpretation({
  interpretation,
  onRemoveNodeType,
  onRemoveTag,
}: SearchInterpretationProps) {
  const hasFilters =
    interpretation.node_types.length > 0 || interpretation.tags.length > 0;

  if (!hasFilters && interpretation.search_terms.length <= 1) return null;

  return (
    <div className="flex items-start gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200">
      <Sparkles className="h-3.5 w-3.5 text-slate-500 mt-0.5 shrink-0" />
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-slate-600">AI zoekt naar:</span>
        {interpretation.search_terms.map((term) => (
          <span
            key={term}
            className="inline-flex items-center px-2 py-0.5 rounded-full bg-white border border-slate-200 text-xs font-medium text-slate-700"
          >
            {term}
          </span>
        ))}

        {interpretation.node_types.length > 0 && (
          <>
            <span className="text-xs text-slate-500">in</span>
            {interpretation.node_types.map((type) => (
              <button
                key={type}
                onClick={() => onRemoveNodeType(type)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary-50 border border-primary-200 text-xs font-medium text-primary-700 hover:bg-primary-100 transition-colors"
              >
                {NODE_TYPE_LABELS[type as NodeType] ?? type}
                <X className="h-3 w-3" />
              </button>
            ))}
          </>
        )}

        {interpretation.tags.length > 0 && (
          <>
            <span className="text-xs text-slate-500">met tag</span>
            {interpretation.tags.map((tag) => (
              <button
                key={tag}
                onClick={() => onRemoveTag(tag)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-xs font-medium text-amber-700 hover:bg-amber-100 transition-colors"
              >
                {tag}
                <X className="h-3 w-3" />
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
