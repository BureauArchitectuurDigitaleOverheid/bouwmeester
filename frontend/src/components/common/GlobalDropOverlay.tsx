import { Upload } from 'lucide-react';
import { useLocation } from 'react-router-dom';

interface GlobalDropOverlayProps {
  visible: boolean;
}

export function GlobalDropOverlay({ visible }: GlobalDropOverlayProps) {
  const location = useLocation();

  if (!visible) return null;

  let message = 'Laat los om een bestand te verwerken';
  if (location.pathname.startsWith('/leads')) {
    message = 'Laat los om een nieuwe lead aan te maken';
  } else if (location.pathname.startsWith('/corpus')) {
    message = 'Laat los om een nieuwe bron toe te voegen';
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 backdrop-blur-sm pointer-events-none">
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-white px-10 py-8 shadow-xl border border-border">
        <div className="rounded-full bg-primary-100 p-4">
          <Upload className="h-8 w-8 text-primary-600" />
        </div>
        <p className="text-base font-medium text-text">{message}</p>
      </div>
    </div>
  );
}
