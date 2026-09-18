import { useMemo, useRef, useState } from 'react';
import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { eventValue, orUndef, useNlddEvent } from '@/components/nldd/events';
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
    <nldd-card>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold flex items-center gap-1.5">
          <Icon name="tag" size="md" />
          Mattermost-kanalen
        </h4>
        <Button variant="secondary" size="sm" icon="plus" onClick={() => setPickerOpen(true)}>
          Kanaal koppelen
        </Button>
      </div>

      {query.isLoading && <LoadingSpinner className="py-6" />}
      {query.isError && (
        <nldd-inline-dialog
          variant="alert"
          size="md"
          text="Kon kanalen niet ophalen."
        />
      )}
      {query.data && query.data.length === 0 && (
        <nldd-inline-dialog
          text={
            scope.type === 'initiatief'
              ? 'Nog geen kanalen gekoppeld.'
              : 'Nog geen kanaal gekoppeld.'
          }
          supporting-text={
            scope.type === 'initiatief'
              ? 'Bouwmeester leest mee in gekoppelde kanalen en stelt nieuwe leads voor.'
              : 'Berichten in gekoppelde kanalen worden notities op deze lead.'
          }
        />
      )}
      {query.data && query.data.length > 0 && (
        <nldd-list type="list" variant="box-tinted" accessible-label="Gekoppelde kanalen">
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
        </nldd-list>
      )}

      <ChannelPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        scope={scope}
        zIndex={(parentZIndex ?? 50) + 10}
      />
    </nldd-card>
  );
}

/** Reads `checked` off an nldd-checkbox-field's `change` detail. */
function checkedValue(event: Event): boolean {
  return Boolean((event as CustomEvent<{ checked?: boolean }>).detail?.checked);
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
  const autoNoteRef = useRef<HTMLElement>(null);
  const suggestRef = useRef<HTMLElement>(null);
  useNlddEvent(autoNoteRef, 'change', (e) => onToggleAutoNote(checkedValue(e)));
  useNlddEvent(suggestRef, 'change', (e) => onToggleSuggest(checkedValue(e)));

  return (
    <nldd-list-item>
      <div className="flex items-start justify-between gap-3 w-full py-1">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <nldd-icon-cell icon="tag" size="16" />
            <nldd-text-cell text={link.channel_display_name} width="fit-content" />
            {link.disabled_at && <nldd-tag color="critical" size="sm" text="uitgeschakeld" />}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            <nldd-checkbox-field
              ref={autoNoteRef}
              label="Berichten als notities"
              checked={orUndef(link.auto_note_enabled)}
            />
            <nldd-checkbox-field
              ref={suggestRef}
              label="Leads voorstellen"
              checked={orUndef(link.suggest_leads_enabled)}
            />
          </div>
        </div>
        <NlddIconButton
          icon="trash"
          accessibleLabel="Ontkoppelen"
          variant="neutral-transparent"
          size="sm"
          onClick={onDelete}
        />
      </div>
    </nldd-list-item>
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

  const searchRef = useRef<HTMLElement>(null);
  useNlddEvent(searchRef, 'input', (e) => setQ(eventValue(e)));

  return (
    <Modal open={open} onClose={onClose} title="Kanaal koppelen" zIndex={zIndex}>
      <div className="space-y-3">
        <p className="text-xs text-text-secondary">
          Zoek een kanaal waar de Bouwmeester-bot al lid van is. Niet
          gevonden? Voeg de bot eerst toe aan dat kanaal in Mattermost.
        </p>
        <nldd-text-field
          ref={searchRef}
          value={q}
          placeholder="Zoek op kanaalnaam"
          keyboard="search"
          accessible-label="Zoek op kanaalnaam"
        />
        {errorMsg && <nldd-inline-dialog variant="alert" text={errorMsg} />}
        {search.isLoading && <LoadingSpinner className="py-4" />}
        {search.data && search.data.length === 0 && debounced.length >= 2 && (
          <nldd-inline-dialog text={`Geen kanalen gevonden voor "${debounced}".`} />
        )}
        {search.data && search.data.length > 0 && (
          <nldd-list
            type="list"
            variant="box-tinted"
            height="288px"
            accessible-label="Gevonden kanalen"
          >
            {search.data.map((ch) => (
              <ChannelSearchRow
                key={ch.channel_id}
                channel={ch}
                pending={createMutation.isPending}
                onPick={() => handlePick(ch)}
              />
            ))}
          </nldd-list>
        )}
        {createMutation.isError && (
          <nldd-inline-dialog
            variant="alert"
            text="Koppelen mislukt"
            supporting-text={
              (createMutation.error as { message?: string } | undefined)?.message ??
              'onbekende fout'
            }
          />
        )}
        <div className="flex justify-end pt-2">
          <nldd-link
            href="https://docs.mattermost.com/welcome/managing-members.html"
            target="_blank"
            size="xs"
            end-icon="external-link"
            text="Bot toevoegen aan kanaal"
          />
        </div>
      </div>
    </Modal>
  );
}

function ChannelSearchRow({
  channel,
  pending,
  onPick,
}: {
  channel: MattermostChannelSearchResult;
  pending: boolean;
  onPick: () => void;
}) {
  return (
    <nldd-list-item>
      <div className="flex items-center justify-between gap-2 w-full">
        <nldd-text-cell
          text={channel.channel_display_name}
          supporting-text={channel.channel_name}
          width="full"
        />
        <Button size="sm" variant="primary" icon="link" onClick={onPick} disabled={pending}>
          Koppelen
        </Button>
      </div>
    </nldd-list-item>
  );
}
