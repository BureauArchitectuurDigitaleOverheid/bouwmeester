import { useCallback, useEffect, useRef, useState } from 'react';
import { DetailSection } from '@/components/common/DetailSection';
import { eventValue, orUndef, useNlddEvent, useNlddValue } from '@/components/nldd/events';
import {
  createAbonnement,
  deleteAbonnement,
  getAbonnementen,
  updateAbonnement,
  type ParlementairAbonnement,
} from '@/api/parlementairAbonnementen';

/**
 * Zoektermen die dit initiatief volgt in nieuwe kamerstukken.
 *
 * Het vangnet staat bewust breed (recall boven precisie), dus de telling
 * per term is het stuurmiddel: een term die niets oplevert is zichtbaar,
 * en een term die vaak wordt weggeklikt ook. Er wordt niets automatisch
 * uitgezet — een term die zichzelf deactiveert levert stil
 * dekkingsverlies op, en dat is erger dan ruis.
 */
export function AbonnementenSection({ initiatiefId }: { initiatiefId: string }) {
  const [abonnementen, setAbonnementen] = useState<ParlementairAbonnement[]>([]);
  const [nieuweTerm, setNieuweTerm] = useState('');
  const [bezig, setBezig] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  const laden = useCallback(async () => {
    try {
      setAbonnementen(await getAbonnementen(initiatiefId));
    } catch {
      setFout('Kon de zoektermen niet ophalen.');
    }
  }, [initiatiefId]);

  useEffect(() => {
    void laden();
  }, [laden]);

  const toevoegen = useCallback(async () => {
    const term = nieuweTerm.trim();
    if (term.length < 3) {
      setFout('Een zoekterm van minder dan drie tekens levert te veel ruis op.');
      return;
    }
    setBezig(true);
    setFout(null);
    try {
      await createAbonnement(initiatiefId, { term });
      setNieuweTerm('');
      await laden();
    } catch (e) {
      // 409 betekent: de term staat er al. Dat is geen fout van de
      // gebruiker maar informatie.
      const status = (e as { status?: number })?.status;
      setFout(
        status === 409
          ? 'Deze term wordt al gevolgd.'
          : 'Toevoegen is niet gelukt.',
      );
    } finally {
      setBezig(false);
    }
  }, [initiatiefId, laden, nieuweTerm]);

  const schakel = useCallback(
    async (abonnement: ParlementairAbonnement) => {
      await updateAbonnement(initiatiefId, abonnement.id, { actief: !abonnement.actief });
      await laden();
    },
    [initiatiefId, laden],
  );

  const verwijder = useCallback(
    async (abonnement: ParlementairAbonnement) => {
      await deleteAbonnement(initiatiefId, abonnement.id);
      await laden();
    },
    [initiatiefId, laden],
  );

  return (
    <DetailSection
      title="Parlementaire signalen"
      count={abonnementen.length}
      separated
    >
      <nldd-container gap="12">
        <nldd-text size="xs" color="secondary">
          Nieuwe kamerstukken waarin een van deze termen voorkomt, verschijnen in de
          gekoppelde Mattermost-kanalen. Er wordt in de volledige tekst gezocht, dus ook
          in bijlagen en beslisnota&apos;s.
        </nldd-text>

        {fout && <nldd-banner variant="critical" size="sm" text={fout} />}

        <nldd-container layout="row" gap="8" vertical-alignment="bottom">
          <TermField value={nieuweTerm} onChange={setNieuweTerm} onSubmit={toevoegen} />
          <nldd-button
            variant="secondary"
            size="sm"
            text="Volgen"
            start-icon="add"
            loading={orUndef(bezig)}
            onClick={toevoegen}
          />
        </nldd-container>

        {abonnementen.length === 0 ? (
          <nldd-text size="xs" color="secondary">
            Nog geen zoektermen. Voeg er een toe, bijvoorbeeld de naam van dit
            initiatief zoals die in kamerstukken wordt geschreven.
          </nldd-text>
        ) : (
          <nldd-table
            columns="minmax(160px,2fr) 90px 110px 120px 80px"
            sm-columns="1fr 80px"
            md-columns="minmax(160px,2fr) 90px 110px"
            accessible-label="Gevolgde zoektermen"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Term" />
              <nldd-text-cell text="Treffers" horizontal-alignment="right" />
              <nldd-cell hide-below="md" horizontal-alignment="right">
                <nldd-text size="xs" weight="bold">Weggeklikt</nldd-text>
              </nldd-cell>
              <nldd-cell hide-below="lg">
                <nldd-text size="xs" weight="bold">Laatste</nldd-text>
              </nldd-cell>
              <nldd-text-cell />
            </nldd-table-row>
            {abonnementen.map((a) => (
              <AbonnementRow
                key={a.id}
                abonnement={a}
                onToggle={() => schakel(a)}
                onDelete={() => verwijder(a)}
              />
            ))}
          </nldd-table>
        )}

        <nldd-text size="xs" color="secondary">
          Een term die niets oplevert is niet per se fout. Een term die vaak wordt
          weggeklikt is waarschijnlijk te breed.
        </nldd-text>
      </nldd-container>
    </DetailSection>
  );
}

/** Een controlled `nldd-text-field` voor een nieuwe zoekterm. */
function TermField({
  value,
  onChange,
  onSubmit,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddValue(ref, value);
  useNlddEvent(
    ref,
    'input',
    useCallback((e: Event) => onChange(eventValue(e)), [onChange]),
  );
  useNlddEvent(
    ref,
    'keydown',
    useCallback(
      (e: Event) => {
        if ((e as KeyboardEvent).key === 'Enter') {
          e.preventDefault();
          onSubmit();
        }
      },
      [onSubmit],
    ),
  );
  return (
    <nldd-text-field
      ref={ref}
      placeholder="Bijvoorbeeld: Nederlandse Digitale Dienst"
      accessible-label="Nieuwe zoekterm"
    />
  );
}

function AbonnementRow({
  abonnement,
  onToggle,
  onDelete,
}: {
  abonnement: ParlementairAbonnement;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const laatste = abonnement.laatste_treffer_op
    ? new Date(abonnement.laatste_treffer_op).toLocaleDateString('nl-NL')
    : '—';

  return (
    <nldd-table-row>
      <nldd-cell>
        <nldd-container layout="row" gap="6" vertical-alignment="center">
          <nldd-text size="xs" color={abonnement.actief ? undefined : 'secondary'}>
            {abonnement.term}
          </nldd-text>
          {!abonnement.actief && <nldd-tag size="sm" color="neutral" text="uit" />}
        </nldd-container>
      </nldd-cell>
      <nldd-text-cell
        text={String(abonnement.treffers)}
        horizontal-alignment="right"
        size="sm"
      />
      {/* `hide-below` bestaat op nldd-cell, niet op nldd-text-cell, dus de
          responsieve kolommen zitten in een nldd-cell eromheen. */}
      <nldd-cell hide-below="md" horizontal-alignment="right">
        <nldd-text size="xs">{abonnement.weggeklikt_totaal}</nldd-text>
      </nldd-cell>
      <nldd-cell hide-below="lg">
        <nldd-text size="xs">{laatste}</nldd-text>
      </nldd-cell>
      <nldd-cell>
        <nldd-container layout="row" gap="4" horizontal-alignment="right">
          <nldd-button
            variant="neutral-transparent"
            size="xs"
            text={abonnement.actief ? 'Pauzeer' : 'Hervat'}
            accessible-label={
              abonnement.actief
                ? `Pauzeer ${abonnement.term}`
                : `Hervat ${abonnement.term}`
            }
            onClick={onToggle}
          />
          <nldd-button
            variant="critical-transparent"
            size="xs"
            start-icon="delete"
            accessible-label={`Verwijder ${abonnement.term}`}
            onClick={onDelete}
          />
        </nldd-container>
      </nldd-cell>
    </nldd-table-row>
  );
}
