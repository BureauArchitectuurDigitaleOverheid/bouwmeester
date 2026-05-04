import { Modal } from '@/components/common/Modal';
import { useAuth, type OnboardingFeature } from '@/contexts/AuthContext';
import { useDismissOnboardingFeature } from '@/hooks/useOnboarding';
import { ProfileStep } from '@/components/onboarding/ProfileStep';
import { MattermostStep } from '@/components/onboarding/MattermostStep';
import { useCallback, useEffect, useRef, type ReactNode } from 'react';

interface StepComponentProps {
  onComplete: () => void;
}

const STEP_COMPONENTS: Record<string, React.ComponentType<StepComponentProps>> = {
  profile: ProfileStep,
  mattermost: MattermostStep,
};

export function OnboardingWizard({
  features,
  stepNumber,
  totalSteps,
}: {
  features: OnboardingFeature[];
  stepNumber: number;
  totalSteps: number;
}) {
  const { refreshAuthStatus } = useAuth();
  const dismissMutation = useDismissOnboardingFeature();
  const dismissAttempted = useRef(false);

  const current = features[0];
  const StepComponent = STEP_COMPONENTS[current.key];

  const handleComplete = useCallback(async () => {
    // Non-dismissible features (profile) clear by saving their underlying
    // data; the backend's check_complete drops them from pending. Calling
    // /dismiss for them returns 422.
    if (current.dismissible) {
      await dismissMutation.mutateAsync({
        featureKey: current.key,
        permanent: true,
      });
    }
    await refreshAuthStatus();
  }, [dismissMutation, current.key, current.dismissible, refreshAuthStatus]);

  const handleDismiss = useCallback(async (permanent: boolean) => {
    await dismissMutation.mutateAsync({
      featureKey: current.key,
      permanent,
    });
    await refreshAuthStatus();
  }, [dismissMutation, current.key, refreshAuthStatus]);

  let footer: ReactNode = null;
  if (current.dismissible) {
    footer = (
      <div className="flex items-center justify-between w-full">
        <button
          onClick={() => handleDismiss(false)}
          disabled={dismissMutation.isPending}
          className="px-4 py-2 rounded-lg border border-border text-sm text-text-secondary hover:text-text hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          Later
        </button>
        <button
          onClick={() => handleDismiss(true)}
          disabled={dismissMutation.isPending}
          className="text-xs text-text-secondary/60 hover:text-text-secondary underline transition-colors disabled:opacity-50"
        >
          Niet meer tonen
        </button>
      </div>
    );
  }

  // Auto-dismiss unknown features to avoid blocking the user.
  // Guard against infinite loops: only attempt once per unknown feature,
  // and skip while a dismiss is already in flight.
  const unknownFeature = !StepComponent;
  useEffect(() => {
    if (unknownFeature && !dismissMutation.isPending && !dismissAttempted.current) {
      dismissAttempted.current = true;
      handleDismiss(false);
    }
  }, [unknownFeature, dismissMutation.isPending, handleDismiss]);

  // Reset the guard when the feature key changes (moved to a known feature).
  useEffect(() => {
    dismissAttempted.current = false;
  }, [current.key]);

  if (unknownFeature) return null;

  const title = totalSteps > 1
    ? `Welkom bij Bouwmeester (stap ${stepNumber} van ${totalSteps})`
    : 'Welkom bij Bouwmeester';

  return (
    <Modal
      open
      onClose={() => {}}
      title={title}
      closeable={false}
      footer={footer}
    >
      <div className="min-h-[350px]">
        <StepComponent onComplete={handleComplete} />
      </div>
    </Modal>
  );
}
