import { ExternalLink, Loader2 } from 'lucide-react';
import { useVersionInfo } from '@/hooks/useAdmin';

const REPO_URL = 'https://github.com/BureauArchitectuurDigitaleOverheid/bouwmeester';

function formatBuildTime(iso: string): string {
  if (!iso) return '–';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('nl-NL', {
    dateStyle: 'long',
    timeStyle: 'short',
    timeZone: 'Europe/Amsterdam',
  });
}

export function SystemInfo() {
  const { data, isLoading, error } = useVersionInfo();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-text-secondary">
        <Loader2 className="h-4 w-4 animate-spin" />
        Laden…
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-red-700">
        Kon versie-informatie niet ophalen.
      </div>
    );
  }

  const sha = data?.git_sha || '';
  const buildTime = data?.build_time || '';
  const hasInfo = sha || buildTime;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold mb-1">Systeem</h2>
        <p className="text-sm text-text-secondary">
          Welke versie van Bouwmeester draait er nu in deze omgeving.
        </p>
      </div>

      {!hasInfo ? (
        <div className="rounded-md border border-border bg-gray-50 p-4 text-sm text-text-secondary">
          Geen versie-informatie beschikbaar. In lokale dev-builds zijn
          <code className="mx-1">GIT_SHA</code> en
          <code className="mx-1">BUILD_TIME</code> niet ingesteld; ze worden
          alleen door de CI-build gevuld.
        </div>
      ) : (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-3 text-sm">
          <dt className="font-medium text-text-secondary">Commit</dt>
          <dd>
            {sha ? (
              <a
                href={`${REPO_URL}/commit/${sha}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-mono text-primary-700 hover:underline"
              >
                {sha}
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            ) : (
              <span className="text-text-secondary">–</span>
            )}
          </dd>

          <dt className="font-medium text-text-secondary">Gebouwd op</dt>
          <dd>{formatBuildTime(buildTime)}</dd>
        </dl>
      )}
    </div>
  );
}
