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

/**
 * The only page outside the auth shell and outside `nldd-app-view`
 * (`/c/:slug` in App.tsx), so it needs its own `nldd-app-view` wrapper for
 * the color-scheme context that every other page gets from AppLayout.
 */
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
      <nldd-app-view background="tinted">
        <nldd-simple-section horizontal-alignment="center" vertical-alignment="center" height="100dvh">
          <LoadingSpinner />
        </nldd-simple-section>
      </nldd-app-view>
    );
  }

  if (status === 'not-found') {
    return (
      <PublicMessage
        title="Pagina niet gevonden"
        body="Deze pagina bestaat niet of is niet (meer) publiek toegankelijk."
      />
    );
  }

  if (status === 'error' || !data) {
    return <PublicMessage title="Er ging iets mis" body="Probeer het later opnieuw." />;
  }

  const accent = data.kleur || DEFAULT_ACCENT;

  return (
    <nldd-app-view background="tinted">
      {/* Top accent stripe — subtiele kleur-identiteit per initiatief */}
      <div aria-hidden className="h-1.5 w-full" style={{ backgroundColor: accent }} />

      <nldd-full-bleed-section width="768px" padding-top="64" padding-bottom="48">
        <nldd-container gap="16">
          <nldd-container layout="row" gap="8" style={{ alignItems: 'center' }}>
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: accent }}
            />
            <nldd-text size="xs" weight="medium" color="secondary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Community
            </nldd-text>
          </nldd-container>
          <nldd-title size={1}>
            <h1>{data.naam}</h1>
          </nldd-title>
          {data.beschrijving && (
            <nldd-container max-width="640px">
              <RichTextDisplay content={data.beschrijving} />
            </nldd-container>
          )}
        </nldd-container>
      </nldd-full-bleed-section>

      <nldd-simple-section width="768px" padding-bottom="80">
        <nldd-container gap="48">
          {data.casussen.length > 0 && (
            <section>
              <nldd-container
                layout="row"
                gap="8"
                horizontal-alignment="left"
                style={{ alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '24px' }}
              >
                <nldd-title size={4}>
                  <h2>Lopende casussen</h2>
                </nldd-title>
                <nldd-text size="sm" color="secondary">
                  {data.casussen.length} {data.casussen.length === 1 ? 'casus' : 'casussen'}
                </nldd-text>
              </nldd-container>
              <nldd-collection layout="grid" item-width="280px" gap="16">
                {data.casussen.map((c, idx) => (
                  <CasusCard key={idx} casus={c} accent={accent} />
                ))}
              </nldd-collection>
            </section>
          )}

          <section>
            <nldd-container
              layout="row"
              gap="8"
              style={{ alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '24px' }}
            >
              <nldd-title size={4}>
                <h2>Updates</h2>
              </nldd-title>
              {data.updates.length > 0 && (
                <nldd-text size="sm" color="secondary">
                  {data.updates.length} {data.updates.length === 1 ? 'bericht' : 'berichten'}
                </nldd-text>
              )}
            </nldd-container>

            {data.updates.length === 0 ? (
              <UpdatesEmptyState naam={data.naam} />
            ) : (
              <nldd-container gap="32">
                {data.updates.map((u, idx) => (
                  <UpdateCard key={idx} update={u} accent={accent} />
                ))}
              </nldd-container>
            )}
          </section>
        </nldd-container>
      </nldd-simple-section>

      <nldd-page-footer width="768px">
        <nldd-container
          layout="row"
          gap="8"
          style={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}
        >
          <nldd-text size="sm" color="secondary">
            Publieke pagina van <strong>{data.naam}</strong>
          </nldd-text>
          <nldd-text size="xs" color="secondary">
            Gepubliceerd via Bouwmeester
          </nldd-text>
        </nldd-container>
      </nldd-page-footer>
    </nldd-app-view>
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
    <nldd-card>
      <div className="relative px-6 py-6 sm:px-8 sm:py-7">
        {/* Kleur-streepje links als verticale accent */}
        <div
          aria-hidden
          className="absolute left-0 top-6 bottom-6 w-1 rounded-r-full"
          style={{ backgroundColor: accent }}
        />
        <nldd-container layout="row" gap="8" style={{ alignItems: 'center', flexWrap: 'wrap', marginBottom: '12px' }}>
          <nldd-text size="xs" weight="medium" color="secondary">
            <time dateTime={update.published_at}>{formattedDate}</time>
          </nldd-text>
          {update.published_by_naam && (
            <nldd-text size="xs" color="secondary">
              · {update.published_by_naam}
            </nldd-text>
          )}
        </nldd-container>
        <nldd-title size={3}>
          <h3>{update.titel}</h3>
        </nldd-title>
        {update.body && (
          <nldd-container padding-top="16">
            <RichTextDisplay content={update.body} />
          </nldd-container>
        )}
      </div>
    </nldd-card>
  );
}

function CasusCard({ casus, accent }: { casus: PublicCasus; accent: string }) {
  return (
    <nldd-card>
      <div className="p-5">
        <nldd-container layout="row" gap="8" style={{ alignItems: 'center', marginBottom: '8px' }}>
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: accent }}
          />
          <nldd-text size="xs" weight="medium" color="secondary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Casus
          </nldd-text>
        </nldd-container>
        <nldd-title size={5}>
          <h3>{casus.titel}</h3>
        </nldd-title>
        {casus.samenvatting && (
          <nldd-container padding-top="8">
            <nldd-text size="sm" color="secondary">
              {casus.samenvatting}
            </nldd-text>
          </nldd-container>
        )}
        {casus.updates.length > 0 && (
          <nldd-container gap="12" padding-top="16" style={{ borderTop: '1px solid var(--color-border)' }}>
            {casus.updates.map((u, idx) => (
              <div key={idx}>
                <nldd-container layout="row" gap="8" style={{ alignItems: 'baseline' }}>
                  <nldd-text size="sm" weight="medium">
                    {u.titel}
                  </nldd-text>
                  <nldd-text size="xs" color="secondary">
                    {new Date(u.published_at).toLocaleDateString('nl-NL', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </nldd-text>
                </nldd-container>
                {u.body_public && (
                  <nldd-text size="sm" color="secondary">
                    {u.body_public}
                  </nldd-text>
                )}
              </div>
            ))}
          </nldd-container>
        )}
      </div>
    </nldd-card>
  );
}

function UpdatesEmptyState({ naam }: { naam: string }) {
  return (
    <nldd-inline-dialog
      icon="megaphone"
      icon-color="accent"
      text="Nog geen updates"
      supporting-text={`Hier verschijnen updates die het team van ${naam} publiceert. Kom later terug, of bookmark deze pagina.`}
    />
  );
}

function PublicMessage({ title, body }: { title: string; body: string }) {
  return (
    <nldd-app-view background="tinted">
      <nldd-simple-section horizontal-alignment="center" vertical-alignment="center" height="100dvh">
        <nldd-container gap="12" horizontal-alignment="center" style={{ textAlign: 'center' }}>
          <nldd-title size={2}>
            <h2>{title}</h2>
          </nldd-title>
          <nldd-text color="secondary">{body}</nldd-text>
        </nldd-container>
      </nldd-simple-section>
    </nldd-app-view>
  );
}
