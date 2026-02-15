import { useRegisterSW } from 'virtual:pwa-register/react';

export function ReloadPrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_swUrl, registration) {
      if (!registration) return;
      // Check for updates every hour
      const id = setInterval(() => registration.update(), 60 * 60 * 1000);
      // Clean up on SW re-registration (defensive)
      return () => clearInterval(id);
    },
  });

  if (!needRefresh) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-auto z-[200] rounded-lg border border-border bg-white px-4 py-3 shadow-lg">
      <p className="text-sm text-text mb-3 sm:mb-0 sm:inline">
        Er is een nieuwe versie beschikbaar.
      </p>
      <div className="flex gap-2 sm:inline-flex sm:ml-3">
        <button
          onClick={() => updateServiceWorker(true)}
          className="flex-1 sm:flex-none rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary/90 transition-colors"
        >
          Bijwerken
        </button>
        <button
          onClick={() => setNeedRefresh(false)}
          className="flex-1 sm:flex-none rounded-md border border-border px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-gray-50 transition-colors"
        >
          Later
        </button>
      </div>
    </div>
  );
}
