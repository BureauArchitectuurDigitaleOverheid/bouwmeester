import { Inbox, CheckSquare, Network, TrendingUp } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { InboxList } from '@/components/inbox/InboxList';
import { EmptyState } from '@/components/common/EmptyState';

export function InboxPage() {
  const navigate = useNavigate();

  // For now, show a welcome state since the inbox API may not be connected
  const inboxItems: [] = [];

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
