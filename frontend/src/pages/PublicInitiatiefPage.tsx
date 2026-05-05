import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getPublicInitiatief } from '@/api/publicInitiatief';
import { ApiError } from '@/api/client';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import type { PublicInitiatief } from '@/types';

type Status = 'loading' | 'ok' | 'not-found' | 'error';

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
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (status === 'not-found') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 bg-gray-50">
        <div className="max-w-md text-center space-y-3">
          <h1 className="text-2xl font-semibold text-text">Pagina niet gevonden</h1>
          <p className="text-text-secondary">
            Deze pagina bestaat niet of is niet (meer) publiek toegankelijk.
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error' || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 bg-gray-50">
        <div className="max-w-md text-center space-y-3">
          <h1 className="text-2xl font-semibold text-text">Er ging iets mis</h1>
          <p className="text-text-secondary">
            Probeer het later opnieuw.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header
        className="px-6 py-10 border-b"
        style={{
          borderColor: data.kleur ?? '#e5e7eb',
          background: data.kleur
            ? `linear-gradient(180deg, ${data.kleur}10 0%, transparent 100%)`
            : undefined,
        }}
      >
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-3 mb-2">
            {data.kleur && (
              <span
                className="inline-block h-4 w-4 rounded-full"
                style={{ backgroundColor: data.kleur }}
              />
            )}
            <h1 className="text-3xl font-semibold text-text">{data.naam}</h1>
          </div>
          {data.beschrijving && (
            <div className="mt-4 text-text-secondary max-w-prose">
              <RichTextDisplay content={data.beschrijving} />
            </div>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        <h2 className="text-lg font-semibold text-text mb-4">Updates</h2>
        {data.updates.length === 0 ? (
          <p className="text-text-secondary">Nog geen updates gepubliceerd.</p>
        ) : (
          <ul className="space-y-6">
            {data.updates.map((u, idx) => (
              <li
                key={idx}
                className="bg-white rounded-xl border border-border p-5 shadow-sm"
              >
                <h3 className="text-base font-semibold text-text">{u.titel}</h3>
                <div className="text-xs text-text-secondary mt-1">
                  {new Date(u.published_at).toLocaleDateString('nl-NL', {
                    day: 'numeric',
                    month: 'long',
                    year: 'numeric',
                  })}
                  {u.published_by_naam && ` · ${u.published_by_naam}`}
                </div>
                {u.body && (
                  <div className="mt-3 text-text">
                    <RichTextDisplay content={u.body} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
