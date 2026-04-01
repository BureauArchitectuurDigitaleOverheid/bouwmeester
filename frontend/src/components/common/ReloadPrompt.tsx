import { useRegisterSW } from 'virtual:pwa-register/react';

export function ReloadPrompt() {
  useRegisterSW({
    onRegisteredSW(_swUrl, registration) {
      if (!registration) return;
      // Check for updates every hour; autoUpdate applies them immediately
      const id = setInterval(() => registration.update(), 60 * 60 * 1000);
      return () => clearInterval(id);
    },
  });

  return null;
}
