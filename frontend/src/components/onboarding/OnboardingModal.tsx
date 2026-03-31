import { useAuth } from '@/contexts/AuthContext';
import { Modal } from '@/components/common/Modal';
import { ProfileStep } from '@/components/onboarding/ProfileStep';

/**
 * Standalone onboarding modal — used for placement re-requests in AppLayout.
 * The onboarding wizard uses ProfileStep directly without this wrapper.
 */
export function OnboardingModal() {
  const { refreshAuthStatus } = useAuth();

  return (
    <Modal
      open
      onClose={() => {}}
      title="Welkom bij Bouwmeester"
      closeable={false}
    >
      <ProfileStep onComplete={refreshAuthStatus} />
    </Modal>
  );
}
