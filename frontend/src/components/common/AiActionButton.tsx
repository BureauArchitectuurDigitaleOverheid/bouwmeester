import { Sparkles, Loader2 } from 'lucide-react';

interface AiActionButtonProps {
  label: string;
  loading: boolean;
  onClick: () => void;
  disabled?: boolean;
  /** Compact style for inline use within step rows */
  compact?: boolean;
}

/**
 * Reusable AI-action button with sparkle icon and loading spinner.
 * Used by TagSuggestions, EdgeSuggestions, GapAnalysisPanel, KompasStepSuggestions.
 */
export function AiActionButton({
  label,
  loading,
  onClick,
  disabled = false,
  compact = false,
}: AiActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading || disabled}
      className={`inline-flex items-center gap-1.5 font-medium rounded-lg text-text-secondary hover:text-text hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
        compact ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-xs border border-border'
      }`}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Sparkles className="h-3.5 w-3.5" />
      )}
      {label}
    </button>
  );
}
