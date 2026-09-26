import { useCallback, useEffect, useRef, type ReactNode } from 'react';
import type { EntityColor } from '@/types';
import { useNlddEvent, useNlddOverlay } from '@/components/nldd/events';

/** Window width per size step. */
const SIZE_WIDTH = {
  sm: 'min(448px, calc(100vw - 32px))',
  md: 'min(512px, calc(100vw - 32px))',
  lg: 'min(672px, calc(100vw - 32px))',
  xl: 'min(896px, calc(100vw - 32px))',
} as const;

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  closeable?: boolean;
  headerIcon?: ReactNode;
  entityLabel?: string;
  accentColor?: EntityColor;
  /** Small back-link above the title for modal stacking navigation */
  backLabel?: string;
  onBack?: () => void;
}

/**
 * `nldd-window` + `nldd-page` as a modal dialog.
 *
 * The window is a native `<dialog>`, always modal, so the browser owns four
 * things a caller never has to: the backdrop, the top layer (stacking needs no
 * z-index of its own), the focus trap, and Escape.
 *
 * The title bar is `nldd-top-title-bar` in the page's sticky header, which
 * supplies the heading, the back affordance and the dismiss button, each with
 * its own accessible name.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  closeable = true,
  headerIcon: _headerIcon,
  entityLabel,
  accentColor,
  backLabel,
  onBack,
}: ModalProps) {
  const windowRef = useRef<HTMLElement>(null);
  const barRef = useRef<HTMLElement>(null);
  const openedAt = useRef(0);

  const handleClose = useCallback(() => {
    // Suppress the close for the first 250ms after opening. Without this, a
    // synthetic click that follows a drag-and-drop (Outlook on Windows/Citrix)
    // lands on the freshly opened window and closes it before the user sees it.
    // Kept from the previous implementation: it was reported from the field.
    if (Date.now() - openedAt.current < 250) return;
    if (!closeable) return;
    onClose();
  }, [closeable, onClose]);

  // Remember when this became visible, for the guard above. In an effect, not
  // during render: a render may run more than once per commit (and does under
  // StrictMode), so a timestamp written there can be re-stamped by a re-render
  // that has nothing to do with opening, and the guard would then swallow a
  // click the user meant.
  //
  // This has to stand BEFORE useNlddOverlay: effects run in the order they are
  // declared, and the overlay's effect is the one that calls show(). Stamped
  // afterwards, the window would be on screen for one effect longer with
  // openedAt still at 0, and a click arriving in that gap reads as 250ms past
  // an open that had not happened yet. That gap is exactly the one the guard
  // exists for.
  useEffect(() => {
    openedAt.current = open ? Date.now() : 0;
  }, [open]);

  useNlddOverlay(windowRef, open, handleClose);

  // The title bar's own dismiss and back buttons.
  useNlddEvent(barRef, 'dismiss', closeable ? onClose : undefined);
  useNlddEvent(barRef, 'back', onBack);

  return (
    <nldd-window
      ref={windowRef}
      accessible-label={title}
      centered
      width={SIZE_WIDTH[size]}
      {...(closeable ? {} : { 'no-light-dismiss': true })}
    >
      {/* A 3px line in the entity color along the top edge, which is how this app
          signals "you are looking at a lead / a node / an opdracht". */}
      {accentColor && (
        <div
          style={{
            height: '3px',
            backgroundColor: `var(--primitives-color-${accentColor}-500)`,
          }}
        />
      )}
      <nldd-page sticky-header {...(footer ? { 'sticky-footer': true } : {})}>
        <nldd-top-title-bar
          ref={barRef}
          slot="header"
          text={title}
          {...(entityLabel ? { 'supporting-text': entityLabel } : {})}
          {...(backLabel && onBack ? { 'back-text': `Terug naar ${backLabel}` } : {})}
          {...(closeable ? { 'dismiss-text': 'Sluiten' } : {})}
        />
        {/* `headerIcon` has nowhere to go: nldd-top-title-bar has only a
            `toolbar` slot, beside the dismiss button, and an icon there would
            read as an action rather than as the entity's type. The type is
            already named in `supporting-text`, so the icon is dropped. */}

        <nldd-container padding="24">{children}</nldd-container>

        {footer && (
          <nldd-container
            slot="footer"
            layout="row"
            gap="12"
            padding="16"
            horizontal-alignment="right"
            vertical-alignment="center"
          >
            {footer}
          </nldd-container>
        )}
      </nldd-page>
    </nldd-window>
  );
}
