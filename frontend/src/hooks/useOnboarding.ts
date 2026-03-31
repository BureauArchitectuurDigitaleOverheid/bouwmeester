import { useMutation, useQuery } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/api/client';
import type { OnboardingFeature } from '@/contexts/AuthContext';

interface DismissParams {
  featureKey: string;
  permanent: boolean;
  personId?: string;
}

export function useDismissOnboardingFeature() {
  return useMutation({
    mutationFn: ({ featureKey, permanent, personId }: DismissParams) =>
      apiPost<{ ok: boolean }>('/api/auth/onboarding/dismiss', {
        feature_key: featureKey,
        permanent,
        person_id: personId ?? null,
      }),
  });
}

/**
 * Fetch pending onboarding features for a person (used in dev mode).
 * In production mode, features come from /auth/status instead.
 */
export function useOnboardingFeatures(personId: string | undefined) {
  return useQuery({
    queryKey: ['onboarding-features', personId],
    queryFn: () =>
      apiGet<OnboardingFeature[]>(`/api/auth/onboarding/features?person_id=${personId}`),
    enabled: !!personId,
  });
}
