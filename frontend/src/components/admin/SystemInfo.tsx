import { AlertTriangle, ExternalLink } from 'lucide-react';
import { useVersionInfo } from '@/hooks/useAdmin';
import { WorkerHealthTable } from './WorkerHealthTable';

const FRONTEND_GIT_SHA = (import.meta.env.VITE_GIT_SHA ?? '') as string;
const FRONTEND_BUILD_TIME = (import.meta.env.VITE_BUILD_TIME ?? '') as string;

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

function CommitLink({ sha, repoUrl }: { sha: string; repoUrl: string }) {
  if (!sha) return <span className="text-text-secondary">–</span>;
  if (!repoUrl) return <span className="font-mono">{sha}</span>;
  return (
    <a
      href={`${repoUrl}/commit/${sha}`}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 font-mono text-primary-700 hover:underline"
    >
      {sha}
      <ExternalLink className="h-3.5 w-3.5" />
    </a>
  );
}

export function SystemInfo() {
  const { data, isLoading, error } = useVersionInfo();

  if (isLoading) return <div className="text-sm text-text-secondary">Laden…</div>;

  if (error) {
    return (
      <div className="text-sm text-red-700">
        Kon versie-informatie niet ophalen.
      </div>
    );
  }

  const backendSha = data?.git_sha || '';
  const backendBuildTime = data?.build_time || '';
  const repoUrl = data?.repo_url || '';
  const hasAny = backendSha || backendBuildTime || FRONTEND_GIT_SHA || FRONTEND_BUILD_TIME;
  const drift = backendSha && FRONTEND_GIT_SHA && backendSha !== FRONTEND_GIT_SHA;

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h2 className="text-lg font-semibold mb-1">Systeem</h2>
        <p className="text-sm text-text-secondary">
          Welke versie van Bouwmeester draait er nu, en zijn de
          achtergrondprocessen gezond.
        </p>
      </div>

      {!hasAny ? (
        <div className="rounded-md border border-border bg-gray-50 p-4 text-sm text-text-secondary">
          Geen versie-informatie beschikbaar. In lokale dev-builds zijn de
          build-args niet gezet; ze worden alleen door de CI-build gevuld.
        </div>
      ) : (
        <>
          {drift ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <div>
                Backend en frontend draaien op verschillende commits. Dit kan
                tijdelijk voorkomen tijdens een deploy, maar mag niet blijvend zijn.
              </div>
            </div>
          ) : null}

          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-3 text-sm">
            <dt className="font-medium text-text-secondary">Backend-commit</dt>
            <dd><CommitLink sha={backendSha} repoUrl={repoUrl} /></dd>

            <dt className="font-medium text-text-secondary">Backend gebouwd</dt>
            <dd>{formatBuildTime(backendBuildTime)}</dd>

            <dt className="font-medium text-text-secondary">Frontend-commit</dt>
            <dd><CommitLink sha={FRONTEND_GIT_SHA} repoUrl={repoUrl} /></dd>

            <dt className="font-medium text-text-secondary">Frontend gebouwd</dt>
            <dd>{formatBuildTime(FRONTEND_BUILD_TIME)}</dd>
          </dl>
        </>
      )}

      <WorkerHealthTable />
    </div>
  );
}
