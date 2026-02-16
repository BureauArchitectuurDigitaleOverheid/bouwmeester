import { useState, useCallback, useRef, useEffect } from 'react';

/**
 * Reusable hook for clipboard copy with auto-reset feedback.
 *
 * Returns `{ copied, copy }` where `copy(text)` writes to the clipboard
 * and sets `copied = true` for a short duration (default 2 s).
 */
export function useCopyToClipboard(resetMs = 2000) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Clean up pending timer on unmount.
  useEffect(() => {
    return () => clearTimeout(timerRef.current);
  }, []);

  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setCopied(false), resetMs);
        return true;
      } catch {
        // Clipboard API not available (e.g. insecure context).
        setCopied(false);
        return false;
      }
    },
    [resetMs],
  );

  return { copied, copy } as const;
}
