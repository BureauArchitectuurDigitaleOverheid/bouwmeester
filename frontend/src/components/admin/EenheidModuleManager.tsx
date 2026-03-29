import { useState, useMemo } from 'react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import {
  useEenheidModules,
  useAvailableModules,
  useUpdateEenheidModule,
} from '@/hooks/useEenheidModules';

const MODULE_DESCRIPTIONS: Record<string, string> = {
  corpus: 'Beleidsdossiers, doelen, instrumenten en hun relaties',
  initiatieven: 'Samenwerkingsinitiatieven met leden en eenheden',
  leads: 'Leads en contacten voor beleidsonderwerpen',
  opdrachten: 'Opdrachten en financieel overzicht',
  taken: 'Taakbeheer gekoppeld aan corpus-items',
};

export function EenheidModuleManager() {
  const { data: allEenheden = [], isLoading: eenhedenLoading } = useOrganisatieFlat();
  const { data: moduleLabels } = useAvailableModules();
  const [selectedEenheidId, setSelectedEenheidId] = useState<string>('');
  const { data: moduleConfig, isLoading: modulesLoading } = useEenheidModules(
    selectedEenheidId || undefined,
  );
  const updateMutation = useUpdateEenheidModule();

  const eenheidOptions = useMemo(
    () => allEenheden.map((e) => ({ value: e.id, label: `${e.naam} (${e.type})` })),
    [allEenheden],
  );

  const handleToggle = async (module: string, currentEnabled: boolean) => {
    if (!selectedEenheidId) return;
    try {
      await updateMutation.mutateAsync({
        eenheidId: selectedEenheidId,
        module,
        enabled: !currentEnabled,
      });
    } catch {
      // React Query handles the error state; mutation.isError will be true
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-text-secondary mb-4">
          Bepaal welke modules beschikbaar zijn per organisatie-eenheid. Uitgeschakelde
          modules worden niet getoond in het menu voor gebruikers van die eenheid.
          Instellingen worden overgenomen door onderliggende eenheden.
        </p>

        <div className="max-w-md">
          <label className="block text-sm font-medium text-text mb-1">
            Organisatie-eenheid
          </label>
          <select
            value={selectedEenheidId}
            onChange={(e) => setSelectedEenheidId(e.target.value)}
            className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
          >
            <option value="">Selecteer een eenheid...</option>
            {eenheidOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {eenhedenLoading && <LoadingSpinner />}

      {selectedEenheidId && modulesLoading && <LoadingSpinner className="py-8" />}

      {updateMutation.isError && (
        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          Kon module-instelling niet opslaan. Probeer het opnieuw.
        </p>
      )}

      {selectedEenheidId && moduleConfig && (
        <div className="rounded-xl border border-border divide-y divide-border">
          {moduleConfig.modules.map((mod) => {
            const isInherited = mod.inherited_from !== null && !mod.enabled;
            const label = moduleLabels?.[mod.module] ?? mod.module;
            const description = MODULE_DESCRIPTIONS[mod.module] ?? '';

            return (
              <div
                key={mod.module}
                className="flex items-center justify-between px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text">{label}</span>
                    {isInherited && (
                      <span className="text-xs text-amber-600 bg-amber-50 rounded px-1.5 py-0.5">
                        Overgenomen van {mod.inherited_from_naam}
                      </span>
                    )}
                  </div>
                  {description && (
                    <p className="text-xs text-text-secondary mt-0.5">{description}</p>
                  )}
                </div>
                <div className="shrink-0 ml-4">
                  <button
                    type="button"
                    role="switch"
                    aria-checked={mod.enabled}
                    disabled={isInherited || updateMutation.isPending}
                    onClick={() => handleToggle(mod.module, mod.enabled)}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:ring-offset-2 ${
                      mod.enabled ? 'bg-primary-600' : 'bg-gray-200'
                    } ${isInherited ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        mod.enabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selectedEenheidId && !modulesLoading && !moduleConfig && (
        <p className="text-sm text-text-secondary py-4">
          Geen configuratie gevonden voor deze eenheid.
        </p>
      )}
    </div>
  );
}
