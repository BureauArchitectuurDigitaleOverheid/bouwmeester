import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getPublicInitiatief } from '@/api/publicInitiatief';
import { ApiError } from '@/api/client';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import type {
  PublicCasus,
  PublicInitiatief,
  PublicInitiatiefUpdate,
} from '@/types';

type Status = 'loading' | 'ok' | 'not-found' | 'error';

const DEFAULT_ACCENT = '#3B82F6';

export function PublicInitiatiefPage() {
  const { slug } = useParams<{ slug: string }>();
  const [status, setStatus] = useState<Status>('loading');
  const [data, setData] = useState<PublicInitiatief | null>(null);

  useEffect(() => {
    // Voorkom indexering door zoekmachines: een initiatief kan ooit publiek
    // hebben gestaan en daarna weer worden gedimd; cached search-results
    // mogen geen interne info blijven serveren.
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex, nofollow, noarchive';
    document.head.appendChild(meta);
    return () => {
      document.head.removeChild(meta);
    };
  }, []);

  useEffect(() => {
    if (data?.naam) document.title = `${data.naam} · Bouwmeester`;
  }, [data?.naam]);

  useEffect(() => {
    if (!slug) {
      setStatus('not-found');
      return;
    }
    let cancelled = false;
    setStatus('loading');
    getPublicInitiatief(slug)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setStatus('ok');
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setStatus('not-found');
        } else {
          setStatus('error');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <LoadingSpinner />
      </div>
    );
  }

  if (status === 'not-found') {
    return <PublicMessage title="Pagina niet gevonden" body="Deze pagina bestaat niet of is niet (meer) publiek toegankelijk." />;
  }

  if (status === 'error' || !data) {
    return <PublicMessage title="Er ging iets mis" body="Probeer het later opnieuw." />;
  }

  const accent = data.kleur || DEFAULT_ACCENT;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top accent stripe — subtiele kleur-identiteit per initiatief */}
      <div className="h-1.5 w-full" style={{ backgroundColor: accent }} />

      <header className="relative overflow-hidden">
        {/* Heel zachte color-wash op de achtergrond, gradient naar wit */}
        <div
          aria-hidden
          className="absolute inset-0"
          style={{
            background: `linear-gradient(180deg, ${accent}14 0%, ${accent}06 35%, transparent 100%)`,
          }}
        />
        <div className="relative max-w-3xl mx-auto px-6 pt-16 pb-12">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500 mb-4">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: accent }}
            />
            Community
          </div>
          <h1 className="text-4xl sm:text-5xl font-semibold text-slate-900 tracking-tight">
            {data.naam}
          </h1>
          {data.beschrijving && (
            <div className="mt-6 text-lg text-slate-600 leading-relaxed max-w-2xl">
              <RichTextDisplay content={data.beschrijving} />
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 max-w-3xl mx-auto w-full px-6 pb-20 space-y-12">
        {data.casussen.length > 0 && (
          <section>
            <div className="flex items-baseline justify-between mt-4 mb-6">
              <h2 className="text-xl font-semibold text-slate-900">
                Lopende casussen
              </h2>
              <span className="text-sm text-slate-500">
                {data.casussen.length}{' '}
                {data.casussen.length === 1 ? 'casus' : 'casussen'}
              </span>
            </div>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {data.casussen.map((c, idx) => (
                <CasusCard key={idx} casus={c} accent={accent} />
              ))}
            </ul>
          </section>
        )}

        <section>
          <div className="flex items-baseline justify-between mt-4 mb-6">
            <h2 className="text-xl font-semibold text-slate-900">Updates</h2>
            {data.updates.length > 0 && (
              <span className="text-sm text-slate-500">
                {data.updates.length}{' '}
                {data.updates.length === 1 ? 'bericht' : 'berichten'}
              </span>
            )}
          </div>

          {data.updates.length === 0 ? (
            <EmptyState accent={accent} naam={data.naam} />
          ) : (
            <ol className="space-y-8">
              {data.updates.map((u, idx) => (
                <UpdateCard key={idx} update={u} accent={accent} />
              ))}
            </ol>
          )}
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-6 text-sm text-slate-500 flex flex-wrap items-center justify-between gap-2">
          <span>
            Publieke pagina van <span className="font-medium text-slate-700">{data.naam}</span>
          </span>
          <span className="text-xs text-slate-400">
            Gepubliceerd via Bouwmeester
          </span>
        </div>
      </footer>
    </div>
  );
}

function UpdateCard({
  update,
  accent,
}: {
  update: PublicInitiatiefUpdate;
  accent: string;
}) {
  const date = new Date(update.published_at);
  const formattedDate = date.toLocaleDateString('nl-NL', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <li className="bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      <article className="relative px-6 py-6 sm:px-8 sm:py-7">
        {/* Kleur-streepje links als verticale accent */}
        <div
          aria-hidden
          className="absolute left-0 top-6 bottom-6 w-1 rounded-r-full"
          style={{ backgroundColor: accent }}
        />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 mb-3">
          <time dateTime={update.published_at} className="font-medium">
            {formattedDate}
          </time>
          {update.published_by_naam && (
            <>
              <span className="text-slate-300">·</span>
              <span>{update.published_by_naam}</span>
            </>
          )}
        </div>
        <h3 className="text-xl sm:text-2xl font-semibold text-slate-900 leading-snug">
          {update.titel}
        </h3>
        {update.body && (
          <div className="mt-4 text-slate-700 leading-relaxed prose-public">
            <RichTextDisplay content={update.body} />
          </div>
        )}
      </article>
    </li>
  );
}

function CasusCard({ casus, accent }: { casus: PublicCasus; accent: string }) {
  return (
    <li className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2 mb-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: accent }}
        />
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
          Casus
        </span>
      </div>
      <h3 className="text-base font-semibold text-slate-900 leading-snug">
        {casus.titel}
      </h3>
      {casus.samenvatting && (
        <p className="mt-2 text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">
          {casus.samenvatting}
        </p>
      )}
    </li>
  );
}

function EmptyState({ accent, naam }: { accent: string; naam: string }) {
  return (
    <div
      className="rounded-2xl border-2 border-dashed border-slate-200 bg-white px-6 py-12 text-center"
    >
      <div
        className="inline-flex items-center justify-center h-12 w-12 rounded-full mb-4"
        style={{ backgroundColor: `${accent}1a` }}
      >
        <svg
          className="h-6 w-6"
          fill="none"
          stroke={accent}
          strokeWidth="2"
          viewBox="0 0 24 24"
          aria-hidden
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"
          />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-slate-900">
        Nog geen updates
      </h3>
      <p className="mt-2 text-sm text-slate-500 max-w-sm mx-auto">
        Hier verschijnen updates die het team van {naam} publiceert. Kom later
        terug, of bookmark deze pagina.
      </p>
    </div>
  );
}

function PublicMessage({ title, body }: { title: string; body: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-slate-50">
      <div className="max-w-md text-center space-y-3">
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        <p className="text-slate-500">{body}</p>
      </div>
    </div>
  );
}
