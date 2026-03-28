import { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { apiGet, apiPut } from '@/api/client';

interface EenheidFeatureConfig {
  organisatie_eenheid_id: string;
  organisatie_eenheid_naam: string;
  features: Record<string, boolean>;
}

interface FeatureDefinition {
  key: string;
  label: string;
  category: string;
}

const FEATURE_DEFINITIONS: FeatureDefinition[] = [
  { key: 'menu.inbox', label: 'Inbox', category: 'Menu' },
  { key: 'menu.corpus', label: 'Corpus', category: 'Menu' },
  { key: 'menu.taken', label: 'Taken', category: 'Menu' },
  { key: 'menu.organisatie', label: 'Organisatie', category: 'Menu' },
  { key: 'menu.eenheid_overzicht', label: 'Eenheid overzicht', category: 'Menu' },
  { key: 'menu.opdrachten', label: 'Opdrachten', category: 'Menu' },
  { key: 'menu.leads', label: 'Leads', category: 'Menu' },
  { key: 'menu.kamerstukken', label: 'Kamerstukken', category: 'Menu' },
  { key: 'menu.zoeken', label: 'Zoeken', category: 'Menu' },
  { key: 'menu.docs', label: 'Documentatie', category: 'Menu' },
  { key: 'header.beleid_architectuur_toggle', label: 'Beleid/Architectuur schakelaar', category: 'Header' },
];

const CATEGORIES = [...new Set(FEATURE_DEFINITIONS.map((f) => f.category))];

export function FeatureTogglesPage() {
  const { person, oidcConfigured, loading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const { data: eenheden, isLoading: eenhedenLoading } = useOrganisatieFlat();
  const [selectedEenheidId, setSelectedEenheidId] = useState<string | null>(null);
  const [localFeatures, setLocalFeatures] = useState<Record<string, boolean>>({});
  const [dirty, setDirty] = useState(false);

  // Fetch feature config for the selected eenheid
  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ['feature-toggles', selectedEenheidId],
    queryFn: () => apiGet<EenheidFeatureConfig>(`/api/feature-toggles/${selectedEenheidId}`),
    enabled: !!selectedEenheidId,
  });

  // When config loads, populate local state
  useEffect(() => {
    if (config) {
      // Initialize all features as true (default), then overlay stored values
      const initial: Record<string, boolean> = {};
      for (const def of FEATURE_DEFINITIONS) {
        initial[def.key] = config.features[def.key] ?? true;
      }
      setLocalFeatures(initial);
      setDirty(false);
    }
  }, [config]);

  // When eenheid changes and no config yet, reset
  useEffect(() => {
    if (!selectedEenheidId) {
      setLocalFeatures({});
      setDirty(false);
    }
  }, [selectedEenheidId]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiPut<EenheidFeatureConfig>(`/api/feature-toggles/${selectedEenheidId}`, {
        toggles: Object.entries(localFeatures).map(([feature_key, enabled]) => ({
          feature_key,
          enabled,
        })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feature-toggles'] });
      setDirty(false);
    },
  });

  if (authLoading) return null;
  if (oidcConfigured && (!person || !person.is_admin)) {
    return <Navigate to="/" replace />;
  }

  const toggleFeature = (key: string) => {
    setLocalFeatures((prev) => ({ ...prev, [key]: !prev[key] }));
    setDirty(true);
  };

  return (
    <div className="max-w-3xl">
      {/* Eenheid selector */}
      <div className="mb-6">
        <label htmlFor="eenheid-select" className="block text-sm font-medium text-text mb-1.5">
          Organisatie-eenheid
        </label>
        <select
          id="eenheid-select"
          value={selectedEenheidId ?? ''}
          onChange={(e) => setSelectedEenheidId(e.target.value || null)}
          className="w-full max-w-md px-3 py-2 rounded-lg border border-border text-sm focus:outline-none focus:border-primary-400"
        >
          <option value="">Selecteer een eenheid...</option>
          {eenheden?.map((e) => (
            <option key={e.id} value={e.id}>
              {e.naam} ({e.type})
            </option>
          ))}
        </select>
        {eenhedenLoading && (
          <p className="text-xs text-text-secondary mt-1">Laden...</p>
        )}
      </div>

      {/* Feature toggles */}
      {selectedEenheidId && (
        <>
          {configLoading ? (
            <p className="text-sm text-text-secondary">Configuratie laden...</p>
          ) : (
            <>
              {CATEGORIES.map((category) => (
                <div key={category} className="mb-6">
                  <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-3">
                    {category}
                  </h3>
                  <div className="space-y-2">
                    {FEATURE_DEFINITIONS.filter((f) => f.category === category).map((def) => (
                      <label
                        key={def.key}
                        className="flex items-center justify-between p-3 rounded-lg border border-border hover:border-border-hover transition-colors cursor-pointer"
                      >
                        <div>
                          <span className="text-sm font-medium text-text">{def.label}</span>
                          <span className="ml-2 text-xs text-text-secondary">{def.key}</span>
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={localFeatures[def.key] ?? true}
                          onClick={() => toggleFeature(def.key)}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                            (localFeatures[def.key] ?? true)
                              ? 'bg-primary-600'
                              : 'bg-gray-300'
                          }`}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              (localFeatures[def.key] ?? true) ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </label>
                    ))}
                  </div>
                </div>
              ))}

              {/* Save button */}
              <div className="flex items-center gap-3 mt-4">
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={!dirty || saveMutation.isPending}
                  className="px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {saveMutation.isPending ? 'Opslaan...' : 'Opslaan'}
                </button>
                {saveMutation.isSuccess && !dirty && (
                  <span className="text-sm text-green-600">Opgeslagen</span>
                )}
                {saveMutation.isError && (
                  <span className="text-sm text-red-600">Opslaan mislukt</span>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
