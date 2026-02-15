import { useState, useMemo } from 'react';
import { Bot, Check, Eye, EyeOff, Loader2, MessageSquare } from 'lucide-react';
import { useAppConfig, useUpdateAppConfig, type AppConfigEntry } from '@/hooks/useAdmin';

interface ConfigGroup {
  label: string;
  description: string;
  icon: React.ReactNode;
  entries: AppConfigEntry[];
}

const GROUP_DEFS: { prefix: string[]; label: string; description: string; icon: React.ReactNode }[] = [
  {
    prefix: ['ANTHROPIC_', 'LLM_', 'VLAM_'],
    label: 'LLM-instellingen',
    description: 'API-sleutels en modelconfiguratie voor Claude en VLAM.',
    icon: <Bot className="h-5 w-5 text-violet-700" />,
  },
  {
    prefix: ['MATTERMOST_'],
    label: 'Mattermost',
    description: 'Configuratie voor de Mattermost-integratie (notificaties, slash-commando\u2019s).',
    icon: <MessageSquare className="h-5 w-5 text-blue-700" />,
  },
];

function groupConfig(entries: AppConfigEntry[]): ConfigGroup[] {
  const groups: ConfigGroup[] = GROUP_DEFS.map((def) => ({
    label: def.label,
    description: def.description,
    icon: def.icon,
    entries: [],
  }));
  const other: AppConfigEntry[] = [];

  for (const entry of entries) {
    const idx = GROUP_DEFS.findIndex((def) =>
      def.prefix.some((p) => entry.key.startsWith(p)),
    );
    if (idx >= 0) {
      groups[idx].entries.push(entry);
    } else {
      other.push(entry);
    }
  }

  // Append ungrouped entries as "Overig" if any
  if (other.length > 0) {
    groups.push({
      label: 'Overig',
      description: 'Overige configuratie.',
      icon: null,
      entries: other,
    });
  }

  return groups.filter((g) => g.entries.length > 0);
}

export function ConfigManager() {
  const { data: config, isLoading } = useAppConfig();
  const groups = useMemo(() => groupConfig(config ?? []), [config]);

  if (isLoading) {
    return <div className="text-sm text-text-secondary py-8 text-center">Laden...</div>;
  }

  return (
    <div className="space-y-6">
      <p className="text-xs text-text-secondary">
        Wijzigingen worden direct actief.
      </p>

      {groups.map((group) => (
        <div key={group.label}>
          <div className="flex items-center gap-2 mb-1">
            {group.icon && (
              <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-gray-100">
                {group.icon}
              </div>
            )}
            <div>
              <h3 className="text-sm font-semibold text-text">{group.label}</h3>
              <p className="text-xs text-text-secondary">{group.description}</p>
            </div>
          </div>
          <div className="space-y-3 mt-3">
            {group.entries.map((entry) => (
              <ConfigRow key={entry.id} entry={entry} />
            ))}
          </div>
        </div>
      ))}

      {groups.length === 0 && (
        <p className="text-sm text-text-secondary py-4 text-center">
          Geen configuratie beschikbaar.
        </p>
      )}
    </div>
  );
}

function ConfigRow({ entry }: { entry: AppConfigEntry }) {
  const updateConfig = useUpdateAppConfig();
  const [value, setValue] = useState(entry.is_secret ? '' : entry.value);
  const [editing, setEditing] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    updateConfig.mutate(
      { key: entry.key, value },
      {
        onSuccess: () => {
          setEditing(false);
          setSaved(true);
          setTimeout(() => setSaved(false), 2000);
        },
      },
    );
  };

  const handleStartEdit = () => {
    if (entry.is_secret) {
      // When editing a secret, start with empty value (user must re-enter)
      setValue('');
    } else {
      setValue(entry.value);
    }
    setEditing(true);
  };

  const displayValue = entry.is_secret ? entry.value : entry.value || '-';

  return (
    <div className="p-4 rounded-xl border border-border bg-white">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-mono font-medium text-text">{entry.key}</span>
            {entry.is_secret && (
              <span className="text-[10px] uppercase tracking-wider font-medium text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                geheim
              </span>
            )}
          </div>
          {entry.description && (
            <p className="text-xs text-text-secondary mb-2">{entry.description}</p>
          )}

          {editing ? (
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  type={entry.is_secret && !showSecret ? 'password' : 'text'}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder={entry.is_secret ? 'Voer nieuwe waarde in...' : 'Waarde...'}
                  className="w-full px-3 py-1.5 text-sm font-mono rounded-lg border border-border focus:outline-none focus:border-primary-400 pr-9"
                  autoFocus
                />
                {entry.is_secret && (
                  <button
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-text-secondary hover:text-text transition-colors"
                  >
                    {showSecret ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                )}
              </div>
              <button
                onClick={handleSave}
                disabled={updateConfig.isPending}
                className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
              >
                {updateConfig.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  'Opslaan'
                )}
              </button>
              <button
                onClick={() => setEditing(false)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-100 text-text hover:bg-gray-200 transition-colors"
              >
                Annuleren
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <code className="text-xs text-text-secondary bg-gray-50 px-2 py-1 rounded font-mono truncate max-w-xs">
                {displayValue}
              </code>
              {saved && (
                <span className="inline-flex items-center gap-1 text-xs text-green-600">
                  <Check className="h-3.5 w-3.5" />
                  Opgeslagen
                </span>
              )}
            </div>
          )}
        </div>

        {!editing && (
          <button
            onClick={handleStartEdit}
            className="text-xs text-primary-700 hover:text-primary-900 transition-colors shrink-0 mt-1"
          >
            Bewerken
          </button>
        )}
      </div>

      {entry.updated_by && (
        <p className="text-[10px] text-text-secondary mt-2">
          Laatst gewijzigd door {entry.updated_by} op{' '}
          {new Date(entry.updated_at).toLocaleDateString('nl-NL', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </p>
      )}
    </div>
  );
}
