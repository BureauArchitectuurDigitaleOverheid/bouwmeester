import { useMemo, useState } from 'react';
import { ExternalLink, Hash, Link2, Plus, Search, Trash2 } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useDebounce } from '@/hooks/useDebounce';
import {
  useCreateInitiatiefChannelLink,
  useCreateLeadChannelLink,
  useDeleteChannelLink,
  useInitiatiefChannels,
  useLeadChannels,
  useSearchMattermostChannels,
  useUpdateChannelLink,
} from '@/hooks/useMattermostChannels';
import type {
  MattermostChannelLink,
  MattermostChannelSearchResult,
} from '@/api/mattermostChannels';

type Scope =
  | { type: 'initiatief'; id: string }
  | { type: 'lead'; id: string };

interface Props {
  scope: Scope;
  /** z-index van de parent-modal (lead/initiatief detail). De picker
   *  opent met +10 bovenop deze waarde zodat hij niet achter de
   *  parent-modal verdwijnt. */
  parentZIndex?: number;
}

export function MattermostChannelsSection({ scope, parentZIndex }: Props) {
  const initiatiefQuery = useInitiatiefChannels(
    scope.type === 'initiatief' ? scope.id : undefined,
  );
  const leadQuery = useLeadChannels(
    scope.type === 'lead' ? scope.id : undefined,
  );
  const query = scope.type === 'initiatief' ? initiatiefQuery : leadQuery;
  const [pickerOpen, setPickerOpen] = useState(false);

  const updateMutation = useUpdateChannelLink(scope);
  const deleteMutation = useDeleteChannelLink(scope);

  return (
    <div className="rounded-2xl border border-border bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold flex items-center gap-1.5">
          <Hash className="h-4 w-4 text-text-secondary" />
          Mattermost-kanalen
        </h4>
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus className="h-3.5 w-3.5" />}
          onClick={() => setPickerOpen(true)}
        >
          Kanaal koppelen
        </Button>
      </div>

      {query.isLoading && <LoadingSpinner className="py-6" />}
      {query.isError && (
        <p className="text-xs text-red-700 px-1 py-2">
          Kon kanalen niet ophalen.
        </p>
      )}
      {query.data && query.data.length === 0 && (
        <p className="text-xs text-text-secondary px-1 py-2">
          {scope.type === 'initiatief'
            ? 'Nog geen kanalen gekoppeld. Bouwmeester leest mee in gekoppelde kanalen en stelt nieuwe leads voor.'
            : 'Nog geen kanaal gekoppeld. Berichten in gekoppelde kanalen worden notities op deze lead.'}
        </p>
      )}
      {query.data && query.data.length > 0 && (
        <ul className="divide-y divide-border rounded-xl border border-border">
          {query.data.map((link) => (
            <ChannelRow
              key={link.id}
              link={link}
              onToggleAutoNote={(value) =>
                updateMutation.mutate({
                  linkId: link.id,
                  data: { auto_note_enabled: value },
                })
              }
              onToggleSuggest={(value) =>
                updateMutation.mutate({
                  linkId: link.id,
                  data: { suggest_leads_enabled: value },
                })
              }
              onDelete={() => deleteMutation.mutate(link.id)}
            />
          ))}
        </ul>
      )}

      <ChannelPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        scope={scope}
        zIndex={(parentZIndex ?? 50) + 10}
      />
    </div>
  );
}

function ChannelRow({
  link,
  onToggleAutoNote,
  onToggleSuggest,
  onDelete,
}: {
  link: MattermostChannelLink;
  onToggleAutoNote: (value: boolean) => void;
  onToggleSuggest: (value: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <li className="px-3 py-2.5 flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm">
          <Hash className="h-3.5 w-3.5 text-text-secondary shrink-0" />
          <span className="font-medium truncate">
            {link.channel_display_name}
          </span>
          {link.disabled_at && (
            <span className="text-xs text-red-700 px-1.5 py-0.5 rounded bg-red-50">
              uitgeschakeld
            </span>
          )}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
          <label className="inline-flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={link.auto_note_enabled}
              onChange={(e) => onToggleAutoNote(e.target.checked)}
            />
            Berichten als notities
          </label>
          <label className="inline-flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={link.suggest_leads_enabled}
              onChange={(e) => onToggleSuggest(e.target.checked)}
            />
            Leads voorstellen
          </label>
        </div>
      </div>
      <button
        type="button"
        onClick={onDelete}
        className="text-text-secondary hover:text-red-600 p-1.5 rounded-md hover:bg-red-50"
        aria-label="Ontkoppelen"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </li>
  );
}

function ChannelPickerModal({
  open,
  onClose,
  scope,
  zIndex,
}: {
  open: boolean;
  onClose: () => void;
  scope: Scope;
  zIndex: number;
}) {
  const [q, setQ] = useState('');
  const debounced = useDebounce(q, 250);
  const search = useSearchMattermostChannels(debounced);
  const createInit = useCreateInitiatiefChannelLink(
    scope.type === 'initiatief' ? scope.id : undefined,
  );
  const createLead = useCreateLeadChannelLink(
    scope.type === 'lead' ? scope.id : undefined,
  );
  const createMutation = scope.type === 'initiatief' ? createInit : createLead;
  const errorMsg = useMemo(() => {
    if (search.isError) {
      const err = search.error as { message?: string } | undefined;
      return err?.message ?? 'Kon Mattermost niet bereiken.';
    }
    return null;
  }, [search.isError, search.error]);

  const handlePick = (ch: MattermostChannelSearchResult) => {
    createMutation.mutate(
      {
        channel_id: ch.channel_id,
        channel_name: ch.channel_name,
        channel_display_name: ch.channel_display_name,
        team_id: ch.team_id,
      },
      {
        onSuccess: () => {
          setQ('');
          onClose();
        },
      },
    );
  };

  return (
    <Modal open={open} onClose={onClose} title="Kanaal koppelen" zIndex={zIndex}>
      <div className="space-y-3">
        <p className="text-xs text-text-secondary">
          Zoek een kanaal waar de Bouwmeester-bot al lid van is. Niet
          gevonden? Voeg de bot eerst toe aan dat kanaal in Mattermost.
        </p>
        <div className="relative">
          <Search className="h-4 w-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-text-secondary" />
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Zoek op kanaalnaam"
            className="w-full pl-8 pr-3 py-2 text-sm rounded-xl border border-border focus:outline-none focus:ring-2 focus:ring-primary-500"
            autoFocus
          />
        </div>
        {errorMsg && (
          <p className="text-xs text-red-700">{errorMsg}</p>
        )}
        {search.isLoading && <LoadingSpinner className="py-4" />}
        {search.data && search.data.length === 0 && debounced.length >= 2 && (
          <p className="text-xs text-text-secondary py-2">
            Geen kanalen gevonden voor "{debounced}".
          </p>
        )}
        {search.data && search.data.length > 0 && (
          <ul className="divide-y divide-border rounded-xl border border-border max-h-72 overflow-y-auto">
            {search.data.map((ch) => (
              <li
                key={ch.channel_id}
                className="px-3 py-2 flex items-center justify-between gap-2 hover:bg-gray-50"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-sm font-medium truncate">
                    <Hash className="h-3.5 w-3.5 text-text-secondary" />
                    {ch.channel_display_name}
                  </div>
                  <div className="text-xs text-text-secondary truncate">
                    {ch.channel_name}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="primary"
                  icon={<Link2 className="h-3.5 w-3.5" />}
                  onClick={() => handlePick(ch)}
                  disabled={createMutation.isPending}
                >
                  Koppelen
                </Button>
              </li>
            ))}
          </ul>
        )}
        {createMutation.isError && (
          <p className="text-xs text-red-700">
            Koppelen mislukt:{' '}
            {(createMutation.error as { message?: string } | undefined)
              ?.message ?? 'onbekende fout'}
          </p>
        )}
        <div className="flex justify-end pt-2">
          <a
            href="https://docs.mattermost.com/welcome/managing-members.html"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-text-secondary hover:text-primary-700"
          >
            <ExternalLink className="h-3 w-3" /> Bot toevoegen aan kanaal
          </a>
        </div>
      </div>
    </Modal>
  );
}
