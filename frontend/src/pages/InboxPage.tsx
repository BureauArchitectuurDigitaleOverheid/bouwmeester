import { useState } from 'react';
import { Inbox, CheckSquare, CheckCheck, Network, TrendingUp, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { InboxList } from '@/components/inbox/InboxList';
import { MessageThread } from '@/components/inbox/MessageThread';
import { EmptyState } from '@/components/common/EmptyState';
import { useNotifications, useDashboardStats, useMarkAllNotificationsRead } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { useEenheidOverview } from '@/hooks/useTasks';
import type { InboxItem } from '@/types';

export function InboxPage() {
  const navigate = useNavigate();
  const [openThreadId, setOpenThreadId] = useState<string | null>(null);

  const { currentPerson } = useCurrentPerson();
  const { data: notifications } = useNotifications(currentPerson?.id);
  const { data: stats } = useDashboardStats(currentPerson?.id);
  const markAllRead = useMarkAllNotificationsRead();
  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);
  const managedEenheid = managedEenheden?.[0] ?? null;
  const managedEenheidId = managedEenheid?.id ?? null;
  const { data: overview } = useEenheidOverview(managedEenheidId);

  const PERSON_LEVEL_TYPES = new Set(['afdeling', 'team', 'cluster']);
  const visibleUnassignedCount = overview
    ? (overview.unassigned_no_unit_count ?? 0) +
      (PERSON_LEVEL_TYPES.has(overview.eenheid_type) ? (overview.unassigned_no_person_count ?? 0) : 0)
    : 0;

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
  };

  const inboxItems: InboxItem[] = (notifications ?? []).map((n) => ({
    id: n.id,
    type: NOTIFICATION_TYPE_MAP[n.type] ?? 'notification',
    title: n.title,
    description: n.message,
    node_id: n.related_node_id,
    sender_name: n.sender_name,
    reply_count: n.reply_count,
    created_at: n.created_at,
    read: n.is_read,
  }));

  const hasUnread = inboxItems.some((item) => !item.read);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Welcome banner */}
      <div className="bg-gradient-to-br from-primary-900 to-primary-700 rounded-2xl p-6 text-white">
        <h2 className="text-xl font-bold mb-1">Welkom bij Bouwmeester</h2>
        <p className="text-white/70 text-sm">
          Beheer uw beleidscorpus, taken en verbindingen op een centrale plek.
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card
          hoverable
          onClick={() => navigate('/corpus')}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-blue-50 text-blue-600">
              <Network className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-text">{stats?.corpus_node_count ?? '-'}</p>
              <p className="text-xs text-text-secondary">Corpus nodes</p>
            </div>
          </div>
        </Card>

        <Card
          hoverable
          onClick={() => navigate('/tasks')}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-amber-50 text-amber-600">
              <CheckSquare className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-text">{stats?.open_task_count ?? '-'}</p>
              <p className="text-xs text-text-secondary">Open taken</p>
            </div>
          </div>
        </Card>

        <Card
          hoverable
          onClick={() => navigate('/tasks')}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-red-50 text-red-600">
              <TrendingUp className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-text">{stats?.overdue_task_count ?? '-'}</p>
              <p className="text-xs text-text-secondary">Achterstallig</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Manager stats card */}
      {managedEenheidId && visibleUnassignedCount > 0 && (
        <Card
          hoverable
          onClick={() => navigate('/eenheid-overzicht')}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-purple-50 text-purple-600">
              <Users className="h-5 w-5" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-text">
                {visibleUnassignedCount} onverdeelde {visibleUnassignedCount === 1 ? 'taak' : 'taken'}
              </p>
              <p className="text-xs text-text-secondary">
                In jouw eenheid - klik om te verdelen
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Inbox section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text">Inbox</h2>
          {hasUnread && currentPerson?.id && (
            <button
              onClick={() => markAllRead.mutate(currentPerson.id)}
              className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 transition-colors"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              Alles gelezen
            </button>
          )}
        </div>

        {inboxItems.length > 0 ? (
          <InboxList items={inboxItems} onOpenThread={setOpenThreadId} />
        ) : (
          <EmptyState
            icon={<Inbox className="h-16 w-16" />}
            title="Inbox is leeg"
            description="Er zijn momenteel geen nieuwe meldingen. Begin met het verkennen van het corpus of het aanmaken van taken."
            action={
              <div className="flex items-center gap-3">
                <Button variant="primary" onClick={() => navigate('/corpus')}>
                  Bekijk corpus
                </Button>
                <Button variant="secondary" onClick={() => navigate('/tasks')}>
                  Bekijk taken
                </Button>
              </div>
            }
          />
        )}
      </div>

      {/* Thread modal */}
      {openThreadId && (
        <MessageThread
          notificationId={openThreadId}
          onClose={() => setOpenThreadId(null)}
        />
      )}
    </div>
  );
}
