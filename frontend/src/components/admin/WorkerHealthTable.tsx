import { useWorkerHealth, type WorkerHealth, type WorkerHeartbeat } from '@/hooks/useAdmin';
import { EmptyState } from '@/components/common/EmptyState';

const LOOP_LABELS: Record<string, string> = {
  parlementair: 'Parlementaire import',
  mattermost_websocket: 'Mattermost: websocket (kanaal-meelezen + DM-koppeling)',
  opdracht_task: 'Opdracht-taken (deadlines, budget)',
  fcc_sync: 'Fortes Change Cloud sync',
};

function formatAge(seconds: number | null): string {
  if (seconds === null) return '–';
  if (seconds < 90) return `${Math.round(seconds)}s geleden`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min geleden`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} uur geleden`;
  return `${Math.round(seconds / 86400)} dagen geleden`;
}

const HEALTH_CONFIG: Record<WorkerHealth, { icon: string; color: 'success' | 'warning' | 'critical' | 'neutral'; label: string }> = {
  healthy: { icon: 'check-mark-circle', color: 'success', label: 'Draait' },
  stale: { icon: 'exclamation-triangle', color: 'warning', label: 'Vertraagd' },
  down: { icon: 'dismiss-circle', color: 'critical', label: 'Niet actief' },
  disabled: { icon: 'minus-circle', color: 'neutral', label: 'Uitgeschakeld' },
};

function HealthBadge({ health }: { health: WorkerHealth }) {
  const { icon, color, label } = HEALTH_CONFIG[health];
  return <nldd-tag text={label} icon={icon} color={color} size="sm" />;
}

function WorkerRow({ worker }: { worker: WorkerHeartbeat }) {
  const label = LOOP_LABELS[worker.loop_name] ?? worker.loop_name;
  return (
    <nldd-table-row>
      <nldd-title-cell text={label} supporting-text={worker.loop_name} />
      <nldd-text-cell>
        <HealthBadge health={worker.health} />
      </nldd-text-cell>
      <nldd-text-cell text={formatAge(worker.seconds_since_last_tick)} hide-below="md" />
      <nldd-text-cell
        text={worker.status === 'never_started' ? 'Nooit gestart' : worker.status}
        color={worker.status === 'never_started' ? 'critical' : 'secondary'}
        supporting-text={worker.detail ?? undefined}
        hide-below="lg"
      />
    </nldd-table-row>
  );
}

export function WorkerHealthTable() {
  const { data, isLoading, error } = useWorkerHealth();

  if (isLoading) {
    return <nldd-text size="sm" color="secondary">Workers laden…</nldd-text>;
  }
  if (error) {
    return (
      <nldd-text size="sm" color="critical">Kon worker-status niet ophalen.</nldd-text>
    );
  }
  if (!data || data.workers.length === 0) {
    return (
      <nldd-text size="sm" color="secondary">Geen worker-data beschikbaar.</nldd-text>
    );
  }

  const anyDown = data.workers.some((w) => w.health === 'down');

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Achtergrondprocessen</h3>
        <nldd-text size="sm" color="secondary">
          De worker draait naast de webserver en doet polling, sync en de Mattermost-websocket. Elke
          loop schrijft hier een hartslag.
        </nldd-text>
      </div>

      {anyDown ? (
        <nldd-inline-dialog
          variant="alert"
          text="Een of meer worker-loops draaien niet"
          supporting-text="Functionaliteit zoals Mattermost-meelezen of FCC-sync werkt nu mogelijk niet. Check de container-logs voor de oorzaak."
        />
      ) : null}

      <nldd-table
        columns="minmax(200px,1fr) 140px 160px minmax(160px,1fr)"
        sm-columns="1fr 140px"
        md-columns="1fr 140px 160px"
        accessible-label="Status achtergrondprocessen"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Loop" />
          <nldd-text-cell text="Status" />
          <nldd-text-cell text="Laatste hartslag" hide-below="md" />
          <nldd-text-cell text="Detail" hide-below="lg" />
        </nldd-table-row>
        {data.workers.map((w) => (
          <WorkerRow key={w.loop_name} worker={w} />
        ))}
        <div slot="empty">
          <EmptyState icon="inbox" title="Geen worker-data beschikbaar" />
        </div>
      </nldd-table>

      <nldd-text size="xs" color="secondary">
        Server-tijd: {new Date(data.server_now).toLocaleString('nl-NL')}. Auto-refresh elke 15 sec.
      </nldd-text>
    </div>
  );
}
