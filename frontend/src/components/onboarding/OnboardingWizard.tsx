import { Modal } from '@/components/common/Modal';
import { useAuth, type OnboardingFeature } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useDismissOnboardingFeature } from '@/hooks/useOnboarding';
import { ProfileStep } from '@/components/onboarding/ProfileStep';
import { MattermostStep } from '@/components/onboarding/MattermostStep';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';

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
  const { oidcConfigured, refreshAuthStatus } = useAuth();
  const { currentPerson } = useCurrentPerson();
  const queryClient = useQueryClient();
  const dismissMutation = useDismissOnboardingFeature();

  const personId = currentPerson?.id ?? undefined;

  const refreshFeatures = async () => {
    if (oidcConfigured) {
      await refreshAuthStatus();
    } else {
      // Dev mode: force refetch the features query so OnboardingGate re-evaluates.
      await queryClient.refetchQueries({ queryKey: ['onboarding-features'] });
    }
  };

  const current = features[0];
  const StepComponent = STEP_COMPONENTS[current.key];

  const handleComplete = async () => {
    await refreshFeatures();
  };

  const handleDismiss = async (permanent: boolean) => {
    await dismissMutation.mutateAsync({
      featureKey: current.key,
      permanent,
      personId,
    });
    await refreshFeatures();
  };

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
  const unknownFeature = !StepComponent;
  useEffect(() => {
    if (unknownFeature) handleDismiss(false);
  }, [unknownFeature]); // eslint-disable-line react-hooks/exhaustive-deps

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
