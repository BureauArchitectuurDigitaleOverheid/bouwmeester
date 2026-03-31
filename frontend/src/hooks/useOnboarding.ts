import { useMutation } from '@tanstack/react-query';
import { apiPost } from '@/api/client';

interface DismissParams {
  featureKey: string;
  permanent: boolean;
}

export function useDismissOnboardingFeature() {
  return useMutation({
    mutationFn: ({ featureKey, permanent }: DismissParams) =>
      apiPost<{ ok: boolean }>('/api/auth/onboarding/dismiss', {
        feature_key: featureKey,
        permanent,
      }),
  });
}
