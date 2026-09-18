import {
  useMattermostChannelOverview,
  type MattermostChannelOverview as Channel,
} from '@/hooks/useAdmin';
import { EmptyState } from '@/components/common/EmptyState';

function formatRelative(iso: string | null): string {
  if (!iso) return 'nog niets gezien';
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.round(ms / 1000)}s geleden`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)} min geleden`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)} uur geleden`;
  return `${Math.round(ms / 86_400_000)} dagen geleden`;
}

function scopeText(channel: Channel): string {
  const label = channel.scope_label ?? '(niet gevonden)';
  const prefix = channel.scope_type === 'lead' ? 'Lead' : 'Initiatief';
  return `${prefix}: ${label}`;
}

function modeCell(channel: Channel) {
  if (channel.disabled_at) {
    return <nldd-tag text="Uitgeschakeld" icon="dismiss-circle" color="critical" size="sm" />;
  }
  if (channel.auto_note_enabled || channel.suggest_leads_enabled) {
    const parts = [
      channel.auto_note_enabled ? 'Notities' : null,
      channel.suggest_leads_enabled ? 'Lead-suggesties' : null,
    ].filter(Boolean);
    return <nldd-tag text={parts.join(' + ')} icon="check-mark-circle" color="success" size="sm" />;
  }
  return <nldd-tag text="Niets actief" icon="minus-circle" color="neutral" size="sm" />;
}

function ChannelRow({ channel }: { channel: Channel }) {
  return (
    <nldd-table-row>
      <nldd-title-cell text={`#${channel.channel_display_name}`} supporting-text={channel.channel_name} />
      <nldd-text-cell text={scopeText(channel)} />
      <nldd-text-cell>{modeCell(channel)}</nldd-text-cell>
      <nldd-text-cell text={formatRelative(channel.last_seen_post_at)} color="secondary" hide-below="md" />
    </nldd-table-row>
  );
}

export function MattermostChannelOverviewTable() {
  const { data, isLoading, error } = useMattermostChannelOverview();

  if (isLoading) {
    return <nldd-text size="sm" color="secondary">Kanalen laden…</nldd-text>;
  }
  if (error) {
    return <nldd-text size="sm" color="critical">Kon kanaaloverzicht niet ophalen.</nldd-text>;
  }
  if (!data || data.length === 0) {
    return (
      <div className="space-y-2">
        <h3 className="text-base font-semibold">Mattermost-kanalen</h3>
        <EmptyState
          icon="message-rectangle-text"
          title="Nog geen kanalen gekoppeld"
          description="Koppel er eentje vanuit een lead of initiatief om hier een overzicht te zien."
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Mattermost-kanalen</h3>
        <nldd-text size="sm" color="secondary">
          Gekoppelde kanalen waar de bot meeleest. &quot;Laatste post&quot; is de meest recente
          verwerkte post; ontbreekt deze, dan is er sinds de koppeling niets binnengekomen, of de
          websocket loopt niet.
        </nldd-text>
      </div>
      <nldd-table
        columns="minmax(200px,1fr) minmax(160px,1fr) 160px 140px"
        sm-columns="1fr 160px"
        accessible-label="Mattermost-kanalen"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Kanaal" />
          <nldd-text-cell text="Gekoppeld aan" hide-below="md" />
          <nldd-text-cell text="Modus" />
          <nldd-text-cell text="Laatste post" hide-below="md" />
        </nldd-table-row>
        {data.map((c) => (
          <ChannelRow key={c.id} channel={c} />
        ))}
        <div slot="empty">
          <EmptyState icon="message-rectangle-text" title="Nog geen kanalen gekoppeld" />
        </div>
      </nldd-table>
    </div>
  );
}
