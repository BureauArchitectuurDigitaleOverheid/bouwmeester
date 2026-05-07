import { CheckCircle2, MinusCircle, XCircle } from 'lucide-react';
import {
  useMattermostChannelOverview,
  type MattermostChannelOverview as Channel,
} from '@/hooks/useAdmin';

function formatRelative(iso: string | null): string {
  if (!iso) return 'nog niets gezien';
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.round(ms / 1000)}s geleden`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)} min geleden`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)} uur geleden`;
  return `${Math.round(ms / 86_400_000)} dagen geleden`;
}

function ScopeLabel({ channel }: { channel: Channel }) {
  const label = channel.scope_label ?? '(niet gevonden)';
  const prefix = channel.scope_type === 'lead' ? 'Lead' : 'Initiatief';
  return (
    <span>
      <span className="text-text-secondary">{prefix}:</span> {label}
    </span>
  );
}

function ChannelRow({ channel }: { channel: Channel }) {
  return (
    <tr className="border-t border-border align-top">
      <td className="py-2 pr-4">
        <div className="font-medium">#{channel.channel_display_name}</div>
        <div className="font-mono text-xs text-text-secondary">{channel.channel_name}</div>
      </td>
      <td className="py-2 pr-4 text-sm">
        <ScopeLabel channel={channel} />
      </td>
      <td className="py-2 pr-4 text-sm">
        {channel.disabled_at ? (
          <span className="inline-flex items-center gap-1 text-red-700">
            <XCircle className="h-3.5 w-3.5" /> Uitgeschakeld
          </span>
        ) : channel.auto_note_enabled || channel.suggest_leads_enabled ? (
          <span className="inline-flex items-center gap-1 text-green-800">
            <CheckCircle2 className="h-3.5 w-3.5" />
            {channel.auto_note_enabled ? 'Notities' : ''}
            {channel.auto_note_enabled && channel.suggest_leads_enabled ? ' + ' : ''}
            {channel.suggest_leads_enabled ? 'Lead-suggesties' : ''}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-text-secondary">
            <MinusCircle className="h-3.5 w-3.5" /> Niets actief
          </span>
        )}
      </td>
      <td className="py-2 pr-4 text-sm text-text-secondary">
        {formatRelative(channel.last_seen_post_at)}
      </td>
    </tr>
  );
}

export function MattermostChannelOverviewTable() {
  const { data, isLoading, error } = useMattermostChannelOverview();

  if (isLoading) {
    return <div className="text-sm text-text-secondary">Kanalen laden…</div>;
  }
  if (error) {
    return (
      <div className="text-sm text-red-700">Kon kanaaloverzicht niet ophalen.</div>
    );
  }
  if (!data || data.length === 0) {
    return (
      <div className="space-y-2">
        <h3 className="text-base font-semibold">Mattermost-kanalen</h3>
        <p className="text-sm text-text-secondary">
          Nog geen kanalen gekoppeld. Koppel er eentje vanuit een lead of
          initiatief om hier een overzicht te zien.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Mattermost-kanalen</h3>
        <p className="text-sm text-text-secondary">
          Gekoppelde kanalen waar de bot meeleest. "Laatste post" is de meest
          recente verwerkte post; ontbreekt deze, dan is er sinds de koppeling
          niets binnengekomen — of de websocket loopt niet.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-text-secondary">
              <th className="py-2 pr-4 font-medium">Kanaal</th>
              <th className="py-2 pr-4 font-medium">Gekoppeld aan</th>
              <th className="py-2 pr-4 font-medium">Modus</th>
              <th className="py-2 pr-4 font-medium">Laatste post</th>
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <ChannelRow key={c.id} channel={c} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
