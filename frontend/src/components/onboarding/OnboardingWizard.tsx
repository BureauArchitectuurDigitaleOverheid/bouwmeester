import { Modal } from '@/components/common/Modal';
import { useAuth, type OnboardingFeature } from '@/contexts/AuthContext';
import { useDismissOnboardingFeature } from '@/hooks/useOnboarding';
import { ProfileStep } from '@/components/onboarding/ProfileStep';
import { MattermostStep } from '@/components/onboarding/MattermostStep';
import { Check } from 'lucide-react';
import type { ReactNode } from 'react';

interface StepComponentProps {
  onComplete: () => void;
}

const STEP_COMPONENTS: Record<string, React.ComponentType<StepComponentProps>> = {
  profile: ProfileStep,
  mattermost: MattermostStep,
};

/** Label map for the stepper (fallback to feature.label from backend). */
const STEP_LABELS: Record<string, string> = {
  profile: 'Profiel',
  mattermost: 'Mattermost',
};

function StepIndicator({
  features,
  currentIndex,
}: {
  features: OnboardingFeature[];
  currentIndex: number;
}) {
  if (features.length <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-0 mb-6">
      {features.map((f, i) => {
        const isDone = i < currentIndex;
        const isCurrent = i === currentIndex;
        const label = STEP_LABELS[f.key] ?? f.label ?? f.key;

        return (
          <div key={f.key} className="flex items-center">
            {/* Connector line (not before first item) */}
            {i > 0 && (
              <div
                className={`w-8 h-0.5 ${isDone ? 'bg-primary-500' : 'bg-border'}`}
              />
            )}
            {/* Circle + label */}
            <div className="flex flex-col items-center">
              <div
                className={`flex items-center justify-center h-7 w-7 rounded-full text-xs font-semibold transition-colors ${
                  isDone
                    ? 'bg-primary-500 text-white'
                    : isCurrent
                      ? 'bg-primary-100 text-primary-700 ring-2 ring-primary-500'
                      : 'bg-gray-100 text-text-secondary'
                }`}
              >
                {isDone ? <Check className="h-4 w-4" /> : i + 1}
              </div>
              <span
                className={`text-[10px] mt-1 whitespace-nowrap ${
                  isCurrent ? 'text-primary-700 font-medium' : 'text-text-secondary'
                }`}
              >
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function OnboardingWizard({ features }: { features: OnboardingFeature[] }) {
  const { refreshAuthStatus } = useAuth();
  const dismissMutation = useDismissOnboardingFeature();

  // Always show the first pending feature.
  const current = features[0];
  const StepComponent = STEP_COMPONENTS[current.key];

  const handleComplete = async () => {
    await refreshAuthStatus();
    // After refresh, if more features remain, OnboardingGate re-renders
    // the wizard with the updated list. If none remain, the app renders.
  };

  const handleDismiss = async (permanent: boolean) => {
    await dismissMutation.mutateAsync({
      featureKey: current.key,
      permanent,
    });
    await refreshAuthStatus();
  };

  // Build footer for dismissible steps.
  let footer: ReactNode = null;
  if (current.dismissible) {
    footer = (
      <div className="flex items-center gap-3 w-full">
        <button
          onClick={() => handleDismiss(false)}
          disabled={dismissMutation.isPending}
          className="text-sm text-text-secondary hover:text-text transition-colors disabled:opacity-50"
        >
          Later
        </button>
        <button
          onClick={() => handleDismiss(true)}
          disabled={dismissMutation.isPending}
          className="text-sm text-text-secondary hover:text-text transition-colors disabled:opacity-50"
        >
          Niet meer tonen
        </button>
      </div>
    );
  }

  if (!StepComponent) {
    // Unknown feature key -- auto-dismiss to avoid blocking the user.
    handleDismiss(false);
    return null;
  }

  return (
    <Modal
      open
      onClose={() => {}}
      title="Welkom bij Bouwmeester"
      closeable={false}
      size="lg"
      footer={footer}
    >
      <StepIndicator features={features} currentIndex={0} />
      <StepComponent onComplete={handleComplete} />
    </Modal>
  );
}
