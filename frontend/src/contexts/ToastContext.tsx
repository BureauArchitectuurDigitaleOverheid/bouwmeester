import { createContext, useCallback, useContext, useRef, useState } from 'react';
import { useNlddEvent } from '@/components/nldd/events';

/** An action offered alongside the message, e.g. undoing what just happened. */
export interface ToastAction {
  label: string;
  onAction: () => void;
}

interface Toast {
  id: number;
  message: string;
  variant: 'error' | 'success' | 'warning';
  action?: ToastAction;
}

interface ToastContextValue {
  showError: (message: string, action?: ToastAction) => void;
  showSuccess: (message: string, action?: ToastAction) => void;
  showWarning: (message: string, action?: ToastAction) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;

/** Our variants in the design system's terms. */
const VARIANTS = {
  error: 'critical',
  warning: 'warning',
  success: 'success',
} as const;

/**
 * One notification.
 *
 * The element runs its own clock and dismisses itself, then fires `dismiss`
 * for the consumer to remove it; this provider keeps no timers of its own. A
 * `critical` notification ignores the clock and waits for the user, so an error
 * never disappears on its own.
 */
function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const ref = useRef<HTMLElement>(null);
  const actionRef = useRef<HTMLElement>(null);

  useNlddEvent(
    ref,
    'dismiss',
    useCallback(() => onDismiss(toast.id), [onDismiss, toast.id]),
  );

  useNlddEvent(
    actionRef,
    'click',
    useCallback(() => {
      toast.action?.onAction();
      onDismiss(toast.id);
    }, [toast, onDismiss]),
  );

  return (
    <nldd-notification
      ref={ref}
      variant={VARIANTS[toast.variant]}
      text={toast.message}
      duration={toast.variant === 'warning' ? 8000 : 5000}
    >
      {toast.action && (
        <div slot="actions">
          <nldd-button
            ref={actionRef}
            variant="inherit-tinted"
            size="sm"
            text={toast.action.label}
          />
        </div>
      )}
    </nldd-notification>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (message: string, variant: Toast['variant'], action?: ToastAction) => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, message, variant, action }]);
    },
    [],
  );

  const showError = useCallback(
    (message: string, action?: ToastAction) => addToast(message, 'error', action),
    [addToast],
  );
  const showSuccess = useCallback(
    (message: string, action?: ToastAction) => addToast(message, 'success', action),
    [addToast],
  );
  const showWarning = useCallback(
    (message: string, action?: ToastAction) => addToast(message, 'warning', action),
    [addToast],
  );

  return (
    <ToastContext.Provider value={{ showError, showSuccess, showWarning }}>
      {children}
      {toasts.length > 0 && (
        // Viewport-fixed stack pinned to a corner. nldd-container has no
        // fixed positioning or z-index, so the outer box is plain CSS and the
        // stacking inside it is an nldd-container.
        <div style={{ position: 'fixed', bottom: '16px', right: '16px', zIndex: 100 }}>
          <nldd-container gap="8">
            {toasts.map((toast) => (
              <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
            ))}
          </nldd-container>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
