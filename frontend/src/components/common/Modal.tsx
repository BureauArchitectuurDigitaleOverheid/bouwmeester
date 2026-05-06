import { useEffect, useRef, type ReactNode } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import type { BadgeVariant } from '@/types';

// Shared counter: tracks how many modals are currently open.
// Only restore body overflow when the last modal closes.
let openModalCount = 0;

const ACCENT_BORDER: Record<BadgeVariant, string> = {
  blue: 'border-t-blue-400',
  green: 'border-t-emerald-400',
  purple: 'border-t-purple-400',
  amber: 'border-t-amber-400',
  cyan: 'border-t-cyan-400',
  rose: 'border-t-rose-400',
  slate: 'border-t-slate-400',
  gray: 'border-t-gray-400',
  red: 'border-t-red-400',
  orange: 'border-t-orange-400',
  emerald: 'border-t-emerald-400',
  indigo: 'border-t-indigo-400',
};

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeable?: boolean;
  /** z-index layer for stacking multiple modals. Higher = on top. Default 50. */
  zIndex?: number;
  headerIcon?: ReactNode;
  entityLabel?: string;
  accentColor?: BadgeVariant;
  /** Small back-link above the title for modal stacking navigation */
  backLabel?: string;
  onBack?: () => void;
}

const sizeClasses = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
};

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  closeable = true,
  zIndex = 50,
  headerIcon,
  entityLabel,
  accentColor,
  backLabel,
  onBack,
}: ModalProps) {
  const wasOpen = useRef(false);
  const openedAtRef = useRef(0);
  useEffect(() => {
    if (open && !wasOpen.current) {
      openModalCount++;
      document.body.style.overflow = 'hidden';
      openedAtRef.current = Date.now();
      wasOpen.current = true;
    } else if (!open && wasOpen.current) {
      openModalCount = Math.max(0, openModalCount - 1);
      if (openModalCount === 0) {
        document.body.style.overflow = '';
      }
      wasOpen.current = false;
    }
    return () => {
      if (wasOpen.current) {
        openModalCount = Math.max(0, openModalCount - 1);
        if (openModalCount === 0) {
          document.body.style.overflow = '';
        }
        wasOpen.current = false;
      }
    };
  }, [open]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && open && closeable) {
        onClose();
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose, closeable]);

  if (!open) return null;

  const borderClass = accentColor ? `border-t-[3px] ${ACCENT_BORDER[accentColor]}` : '';

  // Suppress overlay-click for the first 250ms after opening. Without this,
  // a synthetic mouseup/click that follows a drag-and-drop (notably Outlook
  // on Windows/Citrix) lands on the freshly-mounted overlay and closes the
  // modal before the user sees it.
  const handleOverlayClick = () => {
    if (!closeable) return;
    if (Date.now() - openedAtRef.current < 250) return;
    onClose();
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center" style={{ zIndex }}>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
        onClick={handleOverlayClick}
      />

      {/* Dialog */}
      <div
        className={`relative w-full ${sizeClasses[size]} mx-2 sm:mx-4 bg-surface rounded-2xl shadow-xl border border-border animate-in fade-in zoom-in-95 ${borderClass}`}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-border">
          {backLabel && onBack && (
            <button
              onClick={onBack}
              className="flex items-center gap-1 text-xs text-text-secondary hover:text-text transition-colors mb-1"
            >
              <ArrowLeft className="h-3 w-3" />
              Terug naar {backLabel}
            </button>
          )}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5 min-w-0">
              {headerIcon && (
                <span className="text-text-secondary shrink-0">{headerIcon}</span>
              )}
              <div className="min-w-0">
                {entityLabel && (
                  <span className="text-[10px] font-semibold text-text-secondary uppercase tracking-wider">
                    {entityLabel}
                  </span>
                )}
                <h2 className="text-lg font-semibold text-text truncate">{title}</h2>
              </div>
            </div>
            {closeable && (
              <button
                onClick={onClose}
                className="rounded-lg p-1.5 text-text-secondary hover:bg-gray-100 hover:text-text transition-colors shrink-0"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>

        {/* Body – extra bottom padding so dropdown menus have room to open */}
        <div className="px-6 py-4 max-h-[80vh] sm:max-h-[75vh] overflow-y-auto pb-20">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
