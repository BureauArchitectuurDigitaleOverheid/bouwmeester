import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNlddOverlay } from '@/components/nldd/events';

interface ImageLightboxProps {
  src: string;
  alt: string;
  onClose: () => void;
}

/**
 * A full image in an `nldd-window`.
 *
 * The window is a native modal `<dialog>`, so it lands in the top layer. Opened
 * after a Modal it stacks above that Modal, which a z-index overlay never can.
 * The browser also supplies the backdrop, Escape and a click on the backdrop to
 * close.
 *
 * The window is sized from the image's own dimensions, so a tall image fits
 * the viewport height and a wide one the viewport width without being cropped.
 * It opens once those are known.
 *
 * Portalled to `document.body`: the chat lives inside the split view's
 * inspector pane, and anything left there as a light-DOM child gets slotted
 * into that pane's layout.
 */
export function ImageLightbox({ src, alt, onClose }: ImageLightboxProps) {
  const windowRef = useRef<HTMLElement>(null);
  const [dims, setDims] = useState<{ src: string; width: number; height: number } | null>(null);
  const size = dims?.src === src ? dims : null;

  useEffect(() => {
    const img = new Image();
    let cancelled = false;
    img.onload = () => {
      if (!cancelled) setDims({ src, width: img.naturalWidth, height: img.naturalHeight });
    };
    // Unreadable image: open anyway, nldd-image shows its own error state.
    img.onerror = () => {
      if (!cancelled) setDims({ src, width: 0, height: 0 });
    };
    img.src = src;
    return () => {
      cancelled = true;
    };
  }, [src]);

  useNlddOverlay(windowRef, size !== null, onClose);

  const known = size && size.width > 0 && size.height > 0;
  // Never wider than the image itself, nor so wide that its height overflows
  // the viewport. The window clamps to the viewport width on its own.
  const width = known
    ? `min(${size.width}px, calc((100dvh - 2 * var(--semantics-overlays-inset)) * ${size.width / size.height}))`
    : undefined;

  return createPortal(
    <nldd-window ref={windowRef} accessible-label={alt} centered {...(width ? { width } : {})}>
      {size && (
        <nldd-image
          src={src}
          alt={alt}
          loading="eager"
          object-fit="contain"
          {...(known ? { 'aspect-ratio': `${size.width}/${size.height}` } : {})}
        />
      )}
    </nldd-window>,
    document.body,
  );
}
