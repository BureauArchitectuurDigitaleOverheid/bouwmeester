import { createContext, useContext, useMemo, useCallback } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';

interface FeatureToggleContextValue {
  isFeatureEnabled: (key: string) => boolean;
  features: Record<string, boolean>;
  isLoading: boolean;
}

const FeatureToggleContext = createContext<FeatureToggleContextValue>({
  isFeatureEnabled: () => true,
  features: {},
  isLoading: false,
});

export function FeatureToggleProvider({ children }: { children: ReactNode }) {
  const { data: features, isLoading } = useQuery({
    queryKey: ['feature-toggles', 'my'],
    queryFn: () => apiGet<Record<string, boolean>>('/api/feature-toggles/my'),
    staleTime: 60_000,
  });

  const featuresMap = features ?? {};

  const isFeatureEnabled = useCallback(
    (key: string): boolean => {
      // If the key is not present in the map, default to enabled (true)
      if (featuresMap[key] === undefined) return true;
      return featuresMap[key];
    },
    [featuresMap],
  );

  const value = useMemo(
    () => ({
      isFeatureEnabled,
      features: featuresMap,
      isLoading,
    }),
    [isFeatureEnabled, featuresMap, isLoading],
  );

  return (
    <FeatureToggleContext.Provider value={value}>
      {children}
    </FeatureToggleContext.Provider>
  );
}

export function useFeatureToggle(): FeatureToggleContextValue {
  return useContext(FeatureToggleContext);
}
