import { useEffect, useState } from 'react';
import {
  useMattermostLinkStatus,
  useGenerateLinkCode,
  useUnlinkMattermost,
  type MattermostLinkCode,
} from '@/hooks/useMattermost';
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/hooks/queryKeys';
import { useAuth } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { NlddButton } from '@/components/nldd/NlddLink';
import { Icon } from '@/components/nldd/Icon';

export function MattermostLinkSection({ compact = false }: { compact?: boolean }) {
  const { person: authPerson } = useAuth();
  const { currentPerson } = useCurrentPerson();
  const queryClient = useQueryClient();
  const [linkCode, setLinkCode] = useState<MattermostLinkCode | null>(null);
  const { copied, copy } = useCopyToClipboard();

  // Use auth person ID when available (SSO), fall back to currentPerson (dev mode).
  const personId = authPerson?.id ?? currentPerson?.id ?? undefined;

  const isCodeActive = !!(linkCode && new Date(linkCode.expires_at) > new Date());
  const hasPersonId = !!personId;
  const { data: linkStatus, isLoading, isError } = useMattermostLinkStatus(isCodeActive, hasPersonId, personId);
  const generateCode = useGenerateLinkCode();
  const unlinkMutation = useUnlinkMattermost(personId);

  // When linked while polling, clear the code so the UI switches to the linked state.
  useEffect(() => {
    if (isCodeActive && linkStatus?.linked) {
      setLinkCode(null);
    }
  }, [isCodeActive, linkStatus?.linked]);

  const handleGenerateCode = () => {
    generateCode.mutate(personId, {
      onSuccess: (data) => {
        setLinkCode(data);
      },
    });
  };

  const handleCopyCode = () => {
    if (!linkCode) return;
    copy(`Hoi! Koppel mij alsjeblieft aan Bouwmeester: ${linkCode.code}`);
  };

  const handleUnlink = () => {
    unlinkMutation.mutate(personId, {
      onSuccess: () => setLinkCode(null),
    });
  };

  const content = (
    <>
      {!compact && (
        <nldd-container layout="row" gap="12" style={{ alignItems: 'center', marginBottom: '16px' }}>
          <Icon name="message-rectangle-text" size="lg" />
          <nldd-container gap="2">
            <nldd-text weight="medium">Mattermost koppeling</nldd-text>
            <nldd-text size="sm" color="secondary">
              Koppel je account om Bouwmeester-notificaties in Mattermost te ontvangen.
            </nldd-text>
          </nldd-container>
        </nldd-container>
      )}

      {isLoading ? (
        <nldd-activity-indicator size="20" show-text text="Laden..." />
      ) : isError ? (
        <nldd-banner variant="critical" size="sm" text="Kon koppelingsstatus niet laden. Probeer het later opnieuw." />
      ) : linkStatus?.linked ? (
        <nldd-container gap="12">
          <nldd-banner
            variant="success"
            size="sm"
            text={`Gekoppeld met @${linkStatus.mattermost_username}`}
          />
          <NlddButton
            text="Ontkoppel"
            variant="critical-transparent"
            startIcon="link"
            loading={unlinkMutation.isPending}
            disabled={unlinkMutation.isPending}
            onClick={handleUnlink}
          />
        </nldd-container>
      ) : (
        <nldd-container gap="12">
          {isCodeActive ? (
            <nldd-container gap="12">
              <nldd-card background="tinted">
                <nldd-container gap="8" padding="16">
                  <nldd-text size="sm">
                    Kopieer onderstaand bericht en plak het in een DM naar <strong>@bouwmeester</strong> in
                    Mattermost.
                    {linkStatus?.bot_dm_url && (
                      <>
                        {' '}
                        <nldd-link href={linkStatus.bot_dm_url} target="_blank" text="Open het gesprek met de bot" />
                      </>
                    )}
                  </nldd-text>
                  <nldd-text size="sm" weight="medium">
                    Hoi! Koppel mij alsjeblieft aan Bouwmeester: {linkCode!.code}
                  </nldd-text>
                  <NlddButton
                    text={copied ? 'Gekopieerd!' : 'Kopieer bericht'}
                    startIcon={copied ? 'check-mark' : 'copy'}
                    variant="secondary"
                    size="sm"
                    onClick={handleCopyCode}
                  />
                  <nldd-text size="xs" color="secondary">
                    Code verloopt om{' '}
                    {new Date(linkCode!.expires_at).toLocaleTimeString('nl-NL', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </nldd-text>
                </nldd-container>
              </nldd-card>
              <NlddButton
                text="Annuleren"
                variant="neutral-transparent"
                size="sm"
                onClick={() => {
                  setLinkCode(null);
                  queryClient.invalidateQueries({ queryKey: queryKeys.mattermost.linkStatus(personId) });
                }}
              />
            </nldd-container>
          ) : (
            <NlddButton
              text="Genereer koppelcode"
              startIcon="link"
              loading={generateCode.isPending}
              disabled={generateCode.isPending}
              onClick={handleGenerateCode}
            />
          )}
        </nldd-container>
      )}
    </>
  );

  if (compact) return content;

  return (
    <nldd-card>
      <div className="p-6">{content}</div>
    </nldd-card>
  );
}
