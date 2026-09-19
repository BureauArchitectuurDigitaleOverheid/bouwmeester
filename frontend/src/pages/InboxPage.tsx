import { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { InboxList } from '@/components/inbox/InboxList';
import { MessageThread } from '@/components/inbox/MessageThread';
import { EmptyState } from '@/components/common/EmptyState';
import { useNlddEvent } from '@/components/nldd/events';
import { useNotifications, useDashboardStats, useMarkAllNotificationsRead, useMarkNotificationRead } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useAuth } from '@/contexts/AuthContext';
import { useDismissOnboardingFeature } from '@/hooks/useOnboarding';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { useEenheidOverview } from '@/hooks/useTasks';
import { formatCurrencyCompact } from '@/utils/format';
import type { InboxItem } from '@/types';

const NOTIFICATION_TYPE_MAP: Record<string, string> = {
  task_assigned: 'task',
  task_reassigned: 'task',
  task_completed: 'task',
  task_overdue: 'task',
  edge_created: 'node',
  node_updated: 'node',
  stakeholder_added: 'notification',
  stakeholder_role_changed: 'notification',
  coverage_needed: 'notification',
  politieke_input_imported: 'notification',
  mention: 'notification',
  direct_message: 'message',
  agent_prompt: 'message',
  opdracht_created: 'notification',
  opdracht_status_changed: 'notification',
};

const PERSON_LEVEL_TYPES = new Set(['afdeling', 'dienst', 'bureau', 'cluster', 'team']);

function GettingStartedCard() {
  const navigate = useNavigate();
  const { person, refreshAuthStatus } = useAuth();
  const dismissMutation = useDismissOnboardingFeature();
  const bannerRef = useRef<HTMLElement>(null);

  const showIntro = person?.onboarding_features?.some(
    (f) => f.key === 'intro_handleiding',
  );

  const handleDismiss = useCallback(async () => {
    await dismissMutation.mutateAsync({ featureKey: 'intro_handleiding', permanent: true });
    await refreshAuthStatus();
  }, [dismissMutation, refreshAuthStatus]);
  useNlddEvent(bannerRef, 'dismiss', handleDismiss);

  if (!showIntro) return null;

  return (
    <nldd-banner
      ref={bannerRef}
      variant="accent"
      icon="book"
      text="Nieuw hier?"
      supporting-text="Lees de introductie om te ontdekken wat je met Bouwmeester kunt doen en hoe je snel op weg komt."
      dismissible
    >
      <div slot="actions">
        <Button variant="primary" size="sm" onClick={() => navigate('/docs?tab=introductie')}>
          Ontdek Bouwmeester
        </Button>
      </div>
    </nldd-banner>
  );
}

export function InboxPage() {
  const navigate = useNavigate();
  const [openThreadId, setOpenThreadId] = useState<string | null>(null);

  const { currentPerson } = useCurrentPerson();
  const { data: notifications } = useNotifications();
  const { data: stats } = useDashboardStats();
  const markAllRead = useMarkAllNotificationsRead();
  const markRead = useMarkNotificationRead();
  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);
  const managedEenheid = managedEenheden?.[0] ?? null;
  const managedEenheidId = managedEenheid?.id ?? null;
  const { data: overview } = useEenheidOverview(managedEenheidId);

  const visibleUnassignedCount = overview
    ? (overview.unassigned_no_unit_count ?? 0) +
      (PERSON_LEVEL_TYPES.has(overview.eenheid_type) ? (overview.unassigned_no_person_count ?? 0) : 0)
    : 0;

  const inboxItems: InboxItem[] = (notifications ?? []).map((n) => ({
    id: n.id,
    type: NOTIFICATION_TYPE_MAP[n.type] ?? 'notification',
    notification_type: n.type,
    title: n.title,
    description: n.message,
    node_id: n.related_node_id,
    task_id: n.related_task_id,
    lead_id: n.related_lead_id,
    sender_name: n.sender_name,
    reply_count: n.reply_count,
    created_at: n.created_at,
    read: n.is_read,
  }));

  const hasUnread = inboxItems.some((item) => !item.read);

  return (
    <nldd-simple-section width="960px" horizontal-alignment="center">
      <nldd-container gap="24">
        {/* Welcome banner. The gradient hero has no nldd equivalent (no
            component paints a two-stop brand gradient), so it stays a plain
            styled div; the colors are the same accent step the design system
            itself uses, not an arbitrary Tailwind swatch. */}
        <div
          style={{
            borderRadius: '16px',
            padding: '24px',
            color: 'white',
            background:
              'linear-gradient(to bottom right, var(--primitives-color-lintblauw-900), var(--primitives-color-lintblauw-700))',
          }}
        >
          <nldd-title size={3} color="inherit"><h2>Welkom bij Bouwmeester</h2></nldd-title>
          <nldd-text color="inherit" style={{ opacity: 0.7 }}>
            Je werkplek voor beleid, taken en samenwerking.
          </nldd-text>
        </div>

        {/* Getting started card for new users */}
        <GettingStartedCard />

        {/* Quick stats */}
        <nldd-collection layout="grid" item-width="200px" gap="16">
          <Card hoverable onClick={() => navigate('/corpus')}>
            <nldd-container layout="row" gap="12" vertical-alignment="center">
              <nldd-icon name="network-structure" size="40" color="lintblauw" box />
              <nldd-container gap="0">
                <nldd-text size="lg" weight="bold">{stats?.corpus_node_count ?? '-'}</nldd-text>
                <nldd-text size="xs" color="secondary">Corpus nodes</nldd-text>
              </nldd-container>
            </nldd-container>
          </Card>

          <Card hoverable onClick={() => navigate('/tasks')}>
            <nldd-container layout="row" gap="12" vertical-alignment="center">
              <nldd-icon name="check-list" size="40" color="geel" box />
              <nldd-container gap="0">
                <nldd-text size="lg" weight="bold">{stats?.open_task_count ?? '-'}</nldd-text>
                <nldd-text size="xs" color="secondary">Open taken</nldd-text>
              </nldd-container>
            </nldd-container>
          </Card>

          <Card hoverable onClick={() => navigate('/tasks')}>
            <nldd-container layout="row" gap="12" vertical-alignment="center">
              <nldd-icon name="chart-x-y-axis-line" size="40" color="robijnrood" box />
              <nldd-container gap="0">
                <nldd-text size="lg" weight="bold">{stats?.overdue_task_count ?? '-'}</nldd-text>
                <nldd-text size="xs" color="secondary">Achterstallig</nldd-text>
              </nldd-container>
            </nldd-container>
          </Card>

          <Card
            hoverable
            onClick={() => {
              const params = currentPerson?.id ? `?verantwoordelijke_id=${currentPerson.id}` : '';
              navigate(`/opdrachten${params}`);
            }}
          >
            <nldd-container layout="row" gap="12" vertical-alignment="center">
              <nldd-icon name="euro-sign" size="40" color="mosgroen" box />
              <nldd-container gap="0">
                <nldd-text size="lg" weight="bold" style={{ whiteSpace: 'nowrap' }}>
                  {stats?.active_opdracht_budget != null ? formatCurrencyCompact(stats.active_opdracht_budget) : '-'}
                </nldd-text>
                <nldd-text size="xs" color="secondary">Actief budget</nldd-text>
              </nldd-container>
            </nldd-container>
          </Card>
        </nldd-collection>

        {/* Manager stats card */}
        {managedEenheidId && visibleUnassignedCount > 0 && (
          <Card hoverable onClick={() => navigate('/eenheid-overzicht')}>
            <nldd-container layout="row" gap="12" vertical-alignment="center">
              <nldd-icon name="users" size="40" color="violet" box />
              <nldd-container gap="0" width="full">
                <nldd-text size="sm" weight="medium">
                  {visibleUnassignedCount} onverdeelde {visibleUnassignedCount === 1 ? 'taak' : 'taken'}
                </nldd-text>
                <nldd-text size="xs" color="secondary">
                  In jouw eenheid - klik om te verdelen
                </nldd-text>
              </nldd-container>
            </nldd-container>
          </Card>
        )}

        {/* Inbox section */}
        <nldd-container gap="12">
          <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="center">
            <nldd-title size={4}><h2>Inbox</h2></nldd-title>
            {hasUnread && currentPerson?.id && (
              <Button variant="ghost" size="sm" icon="check-list" onClick={() => markAllRead.mutate()}>
                Alles gelezen
              </Button>
            )}
          </nldd-container>

          {inboxItems.length > 0 ? (
            <InboxList items={inboxItems} onOpenThread={setOpenThreadId} onMarkRead={(id) => markRead.mutate(id)} />
          ) : (
            <EmptyState
              icon="inbox"
              title="Inbox is leeg"
              description="Er zijn momenteel geen nieuwe meldingen. Begin met het verkennen van het corpus of het aanmaken van taken."
              action={
                <nldd-container layout="row" gap="12" vertical-alignment="center">
                  <Button variant="primary" onClick={() => navigate('/corpus')}>
                    Bekijk corpus
                  </Button>
                  <Button variant="secondary" onClick={() => navigate('/tasks')}>
                    Bekijk taken
                  </Button>
                </nldd-container>
              }
            />
          )}
        </nldd-container>

        {/* Thread modal */}
        {openThreadId && (
          <MessageThread
            notificationId={openThreadId}
            onClose={() => setOpenThreadId(null)}
          />
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
