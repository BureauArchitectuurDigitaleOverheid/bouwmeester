import { useState, useCallback } from 'react';
import { suggestTags } from '@/api/llm';

interface AutoTagState {
  showDialog: boolean;
  matchedTags: string[];
  suggestedNewTags: string[];
}

/**
 * Hook for auto-tag suggestion on save.
 * Call `checkAndSuggest` before saving — it returns true if the dialog was shown
 * (meaning the caller should wait), or false if save can proceed immediately.
 */
export function useAutoTagSuggestion() {
  const [state, setState] = useState<AutoTagState>({
    showDialog: false,
    matchedTags: [],
    suggestedNewTags: [],
  });

  const checkAndSuggest = useCallback(
    async (params: {
      title: string;
      description?: string;
      nodeType: string;
      currentTagCount: number;
      existingTagNames?: string[];
      pendingTagNames?: string[];
    }): Promise<boolean> => {
      if (params.currentTagCount >= 2) return false;

      try {
        const timeout = setTimeout(() => {}, 3000);
        const res = await suggestTags({
          title: params.title.trim(),
          description: params.description?.trim() || undefined,
          node_type: params.nodeType,
        });
        clearTimeout(timeout);

        if (!res.available) return false;
        if (res.matched_tags.length === 0 && res.suggested_new_tags.length === 0) return false;

        // Filter out already-known tags
        const known = new Set([
          ...(params.existingTagNames ?? []).map((n) => n.toLowerCase()),
          ...(params.pendingTagNames ?? []).map((n) => n.toLowerCase()),
        ]);
        const matched = res.matched_tags.filter((t) => !known.has(t.toLowerCase()));
        const newTags = res.suggested_new_tags.filter((t) => !known.has(t.toLowerCase()));

        if (matched.length === 0 && newTags.length === 0) return false;

        setState({ showDialog: true, matchedTags: matched, suggestedNewTags: newTags });
        return true;
      } catch {
        return false;
      }
    },
    [],
  );

  const closeDialog = useCallback(() => {
    setState((prev) => ({ ...prev, showDialog: false }));
  }, []);

  return {
    showAutoTagDialog: state.showDialog,
    autoTagMatched: state.matchedTags,
    autoTagNew: state.suggestedNewTags,
    checkAndSuggest,
    closeAutoTagDialog: closeDialog,
  };
}
