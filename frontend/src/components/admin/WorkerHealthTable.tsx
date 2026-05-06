import { CheckCircle2, AlertTriangle, XCircle, MinusCircle } from 'lucide-react';
import { useWorkerHealth, type WorkerHealth, type WorkerHeartbeat } from '@/hooks/useAdmin';

const LOOP_LABELS: Record<string, string> = {
  parlementair: 'Parlementaire import',
  mattermost_link: 'Mattermost: account-koppeling (DM-poller)',
  mattermost_websocket: 'Mattermost: meelezen in kanalen (websocket)',
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

function HealthBadge({ health }: { health: WorkerHealth }) {
  const config: Record<WorkerHealth, { Icon: typeof CheckCircle2; cls: string; label: string }> = {
    healthy: {
      Icon: CheckCircle2,
      cls: 'bg-green-100 text-green-800 border-green-200',
      label: 'Draait',
    },
    stale: {
      Icon: AlertTriangle,
      cls: 'bg-amber-100 text-amber-900 border-amber-200',
      label: 'Vertraagd',
    },
    down: {
      Icon: XCircle,
      cls: 'bg-red-100 text-red-800 border-red-200',
      label: 'Niet actief',
    },
    disabled: {
      Icon: MinusCircle,
      cls: 'bg-gray-100 text-gray-700 border-gray-200',
      label: 'Uitgeschakeld',
    },
  };
  const { Icon, cls, label } = config[health];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}

function WorkerRow({ worker }: { worker: WorkerHeartbeat }) {
  const label = LOOP_LABELS[worker.loop_name] ?? worker.loop_name;
  return (
    <tr className="border-t border-border align-top">
      <td className="py-2 pr-4">
        <div className="font-medium">{label}</div>
        <div className="font-mono text-xs text-text-secondary">{worker.loop_name}</div>
      </td>
      <td className="py-2 pr-4">
        <HealthBadge health={worker.health} />
      </td>
      <td className="py-2 pr-4 text-sm">{formatAge(worker.seconds_since_last_tick)}</td>
      <td className="py-2 pr-4 text-sm text-text-secondary">
        {worker.status === 'never_started' ? (
          <span className="text-red-700">Nooit gestart</span>
        ) : (
          worker.status
        )}
        {worker.detail ? (
          <div className="mt-0.5 text-xs text-text-secondary">{worker.detail}</div>
        ) : null}
      </td>
    </tr>
  );
}

export function WorkerHealthTable() {
  const { data, isLoading, error } = useWorkerHealth();

  if (isLoading) {
    return <div className="text-sm text-text-secondary">Workers laden…</div>;
  }
  if (error) {
    return (
      <div className="text-sm text-red-700">
        Kon worker-status niet ophalen.
      </div>
    );
  }
  if (!data || data.workers.length === 0) {
    return (
      <div className="text-sm text-text-secondary">
        Geen worker-data beschikbaar.
      </div>
    );
  }

  const anyDown = data.workers.some((w) => w.health === 'down');

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Achtergrondprocessen</h3>
        <p className="text-sm text-text-secondary">
          De worker draait naast de webserver en doet polling, sync en de
          Mattermost-websocket. Elke loop schrijft hier een hartslag.
        </p>
      </div>

      {anyDown ? (
        <div className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            Een of meer worker-loops draaien niet. Functionaliteit zoals
            Mattermost-meelezen of FCC-sync werkt nu mogelijk niet. Check de
            container-logs voor de oorzaak.
          </div>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-text-secondary">
              <th className="py-2 pr-4 font-medium">Loop</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 pr-4 font-medium">Laatste hartslag</th>
              <th className="py-2 pr-4 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {data.workers.map((w) => (
              <WorkerRow key={w.loop_name} worker={w} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-text-secondary">
        Server-tijd: {new Date(data.server_now).toLocaleString('nl-NL')}. Auto-refresh elke 15 sec.
      </p>
    </div>
  );
}
