import { Modal } from '@/components/common/Modal';
import { useAuth, type OnboardingFeature } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useDismissOnboardingFeature } from '@/hooks/useOnboarding';
import { ProfileStep } from '@/components/onboarding/ProfileStep';
import { MattermostStep } from '@/components/onboarding/MattermostStep';
import { useQueryClient } from '@tanstack/react-query';
import { Check } from 'lucide-react';
import type { ReactNode } from 'react';

interface StepComponentProps {
  onComplete: () => void;
}

const STEP_COMPONENTS: Record<string, React.ComponentType<StepComponentProps>> = {
  profile: ProfileStep,
  mattermost: MattermostStep,
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
    <div className="mb-6">
      {/* Row 1: circles + connectors — all vertically centered */}
      <div className="flex items-center justify-center">
        {features.map((f, i) => {
          const isDone = i < currentIndex;
          const isCurrent = i === currentIndex;
          return (
            <div key={f.key} className="flex items-center">
              {i > 0 && (
                <div className={`w-16 h-0.5 ${isDone ? 'bg-primary-500' : 'bg-border'}`} />
              )}
              <div
                className={`flex items-center justify-center h-8 w-8 shrink-0 rounded-full text-xs font-semibold transition-colors ${
                  isDone
                    ? 'bg-primary-500 text-white'
                    : isCurrent
                      ? 'bg-primary-100 text-primary-700 ring-2 ring-primary-500'
                      : 'bg-gray-100 text-text-secondary'
                }`}
              >
                {isDone ? <Check className="h-4 w-4" /> : i + 1}
              </div>
            </div>
          );
        })}
      </div>
      {/* Row 2: labels — mirrored spacing so they sit under their circles */}
      <div className="flex items-center justify-center mt-1.5">
        {features.map((f, i) => {
          const isCurrent = i === currentIndex;
          return (
            <div key={f.key} className="flex items-center">
              {i > 0 && <div className="w-16" />}
              <span
                className={`w-8 text-center text-[11px] ${
                  isCurrent ? 'text-primary-700 font-medium' : 'text-text-secondary'
                }`}
                style={{ minWidth: 72 }}
              >
                {f.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function OnboardingWizard({ features }: { features: OnboardingFeature[] }) {
  const { oidcConfigured, refreshAuthStatus } = useAuth();
  const { currentPerson } = useCurrentPerson();
  const queryClient = useQueryClient();
  const dismissMutation = useDismissOnboardingFeature();

  const personId = currentPerson?.id ?? undefined;

  const refreshFeatures = async () => {
    if (oidcConfigured) {
      await refreshAuthStatus();
    } else {
      // Dev mode: invalidate the features query so OnboardingGate re-evaluates.
      await queryClient.invalidateQueries({ queryKey: ['onboarding-features'] });
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
    handleDismiss(false);
    return null;
  }

  return (
    <Modal
      open
      onClose={() => {}}
      title="Welkom bij Bouwmeester"
      closeable={false}
      footer={footer}
    >
      <StepIndicator features={features} currentIndex={0} />
      <StepComponent onComplete={handleComplete} />
    </Modal>
  );
}
