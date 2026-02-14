import { useRegisterSW } from 'virtual:pwa-register/react';

export function ReloadPrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_swUrl, registration) {
      if (!registration) return;
      // Check for updates every hour
      setInterval(() => registration.update(), 60 * 60 * 1000);
    },
  });

  if (!needRefresh) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-lg border border-border bg-white px-4 py-3 shadow-lg">
      <span className="text-sm text-text">Nieuwe versie beschikbaar</span>
      <button
        onClick={() => updateServiceWorker(true)}
        className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary/90 transition-colors"
      >
        Bijwerken
      </button>
      <button
        onClick={() => setNeedRefresh(false)}
        className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-gray-50 transition-colors"
      >
        Later
      </button>
    </div>
  );
}
