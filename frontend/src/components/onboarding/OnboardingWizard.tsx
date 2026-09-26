import { Modal } from '@/components/common/Modal';
import { useAuth, type OnboardingFeature } from '@/contexts/AuthContext';
import {
  useDismissOnboardingFeature,
  useRefreshOnboardingFeatures,
} from '@/hooks/useOnboarding';
import { ProfileStep } from '@/components/onboarding/ProfileStep';
import { MattermostStep } from '@/components/onboarding/MattermostStep';
import { NlddButton } from '@/components/nldd/NlddButton';
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
  const refreshMutation = useRefreshOnboardingFeatures();
  const dismissAttempted = useRef(false);

  const current = features[0];
  const StepComponent = STEP_COMPONENTS[current.key];

  const handleComplete = useCallback(async () => {
    // A step is "complete" when its underlying data exists; the backend's
    // check_complete drops it from pending on the next /status call. We
    // pop the session cache first so the recomputation actually runs.
    await refreshMutation.mutateAsync();
    await refreshAuthStatus();
  }, [refreshMutation, refreshAuthStatus]);

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
      <nldd-container layout="row" vertical-alignment="center" width="full">
        <NlddButton
          text="Later"
          variant="neutral-transparent"
          disabled={dismissMutation.isPending}
          onClick={() => handleDismiss(false)}
        />
        <nldd-spacer size="flexible" direction="horizontal" />
        <NlddButton
          text="Niet meer tonen"
          variant="neutral-transparent"
          size="sm"
          disabled={dismissMutation.isPending}
          onClick={() => handleDismiss(true)}
        />
      </nldd-container>
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
      {/* No nldd-container attribute sets a min-height (only the cell family does),
          so this stays a plain div. It reserves vertical space between steps of
          differing height, purely a layout dimension, not a color or utility class. */}
      <div style={{ minHeight: '350px' }}>
        <StepComponent onComplete={handleComplete} />
      </div>
    </Modal>
  );
}
