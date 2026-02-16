import { useEffect, useState } from 'react';
import { Loader2, MessageSquare, Link2, Unlink, Copy, Check } from 'lucide-react';
import {
  useMattermostLinkStatus,
  useGenerateLinkCode,
  useUnlinkMattermost,
  type MattermostLinkCode,
} from '@/hooks/useMattermost';
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/hooks/queryKeys';

export function MattermostLinkSection() {
  const queryClient = useQueryClient();
  const [linkCode, setLinkCode] = useState<MattermostLinkCode | null>(null);
  const { copied, copy } = useCopyToClipboard();

  // Poll for link status changes while a code is active.
  const isCodeActive = !!(linkCode && new Date(linkCode.expires_at) > new Date());
  const { data: linkStatus, isLoading, isError } = useMattermostLinkStatus(isCodeActive);
  const generateCode = useGenerateLinkCode();
  const unlinkMutation = useUnlinkMattermost();

  // When linked while polling, clear the code so the UI switches to the linked state.
  useEffect(() => {
    if (isCodeActive && linkStatus?.linked) {
      setLinkCode(null);
    }
  }, [isCodeActive, linkStatus?.linked]);

  const handleGenerateCode = () => {
    generateCode.mutate(undefined, {
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
    unlinkMutation.mutate();
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-blue-100">
          <MessageSquare className="h-5 w-5 text-blue-700" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-text">Mattermost koppeling</h2>
          <p className="text-sm text-text-secondary">
            Koppel je account om Bouwmeester-notificaties in Mattermost te ontvangen.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-text-secondary py-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          Laden...
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Kon koppelingsstatus niet laden. Probeer het later opnieuw.
        </div>
      ) : linkStatus?.linked ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3">
            <Link2 className="h-4 w-4 text-green-600" />
            <span className="text-sm text-green-800">
              Gekoppeld met <strong>@{linkStatus.mattermost_username}</strong>
            </span>
          </div>
          <button
            onClick={handleUnlink}
            disabled={unlinkMutation.isPending}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-red-200 text-red-600 text-sm font-medium hover:bg-red-50 transition-colors disabled:opacity-50"
          >
            {unlinkMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Unlink className="h-4 w-4" />
            )}
            Ontkoppel
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {isCodeActive ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                <p className="text-sm text-blue-800 mb-2">
                  Kopieer het bericht en stuur het als DM naar <strong>@bouwmeester</strong> in Mattermost:
                </p>
                <div className="rounded-md bg-white border border-blue-200 px-3 py-2 text-sm text-blue-900">
                  Hoi! Koppel mij alsjeblieft aan Bouwmeester: <strong className="font-mono">{linkCode!.code}</strong>
                </div>
                <button
                  onClick={handleCopyCode}
                  className="mt-2 flex items-center gap-1.5 px-3 py-2 rounded-lg border border-blue-200 text-blue-700 text-sm hover:bg-blue-100 transition-colors"
                >
                  {copied ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                  {copied ? 'Gekopieerd!' : 'Kopieer bericht'}
                </button>
                <p className="text-xs text-blue-600 mt-2">
                  Code verloopt om {new Date(linkCode!.expires_at).toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
              <button
                onClick={() => {
                  setLinkCode(null);
                  queryClient.invalidateQueries({ queryKey: queryKeys.mattermost.linkStatus });
                }}
                className="text-sm text-text-secondary hover:text-text transition-colors"
              >
                Annuleren
              </button>
            </div>
          ) : (
            <button
              onClick={handleGenerateCode}
              disabled={generateCode.isPending}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"
            >
              {generateCode.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Link2 className="h-4 w-4" />
              )}
              Genereer koppelcode
            </button>
          )}
        </div>
      )}
    </div>
  );
}
