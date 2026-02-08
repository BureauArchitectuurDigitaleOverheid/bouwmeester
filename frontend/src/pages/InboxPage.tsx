import { Inbox, CheckSquare, Network, TrendingUp, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { InboxList } from '@/components/inbox/InboxList';
import { EmptyState } from '@/components/common/EmptyState';
import { useNotifications } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { useEenheidOverview } from '@/hooks/useTasks';
import type { InboxItem } from '@/types';

export function InboxPage() {
  const navigate = useNavigate();

  const { currentPerson } = useCurrentPerson();
  const { data: notifications } = useNotifications(currentPerson?.id);
  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);
  const managedEenheidId = managedEenheden?.[0]?.id ?? null;
  const { data: overview } = useEenheidOverview(managedEenheidId);

  const inboxItems: InboxItem[] = (notifications ?? []).map((n) => ({
    id: n.id,
    type: n.type === 'direct_message' || n.type === 'agent_prompt' ? 'message' : 'notification',
    title: n.title,
    description: n.message,
    node_id: n.related_node_id,
    created_at: n.created_at,
    read: n.is_read,
  }));

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
              <p className="text-2xl font-bold text-text">-</p>
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
              <p className="text-2xl font-bold text-text">-</p>
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
              <p className="text-2xl font-bold text-text">-</p>
              <p className="text-xs text-text-secondary">Achterstallig</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Manager stats card */}
      {managedEenheidId && overview && overview.unassigned_count > 0 && (
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
                {overview.unassigned_count} onverdeelde {overview.unassigned_count === 1 ? 'taak' : 'taken'}
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
        </div>

        {inboxItems.length > 0 ? (
          <InboxList items={inboxItems} />
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
    </div>
  );
}
