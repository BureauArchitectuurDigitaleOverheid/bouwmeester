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

  // Alleen het nieuwste verzoek mag de state schrijven. De modal wordt
  // hergebruikt tussen initiatieven, dus een traag antwoord van het vorige
  // initiatief kan anders over het nieuwe heen landen.
  const verzoekTeller = useRef(0);

  const laden = useCallback(async () => {
    const mijnVerzoek = ++verzoekTeller.current;
    try {
      const data = await getAbonnementen(initiatiefId);
      if (mijnVerzoek === verzoekTeller.current) setAbonnementen(data);
    } catch {
      if (mijnVerzoek === verzoekTeller.current) {
        setFout('Kon de zoektermen niet ophalen.');
      }
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

  // Welke rij een mutatie heeft lopen. Zonder dit vuurt een dubbelklik
  // twee PATCH-calls, en kunnen de antwoorden in omgekeerde volgorde
  // binnenkomen — dan staat de pil op het tegenovergestelde van wat de
  // server weet.
  const [bezigeRij, setBezigeRij] = useState<string | null>(null);

  const schakel = useCallback(
    async (abonnement: ParlementairAbonnement) => {
      if (bezigeRij) return;
      setBezigeRij(abonnement.id);
      setFout(null);
      try {
        await updateAbonnement(initiatiefId, abonnement.id, {
          actief: !abonnement.actief,
        });
        await laden();
      } catch {
        setFout(`Kon '${abonnement.term}' niet aanpassen.`);
      } finally {
        setBezigeRij(null);
      }
    },
    [bezigeRij, initiatiefId, laden],
  );

  const verwijder = useCallback(
    async (abonnement: ParlementairAbonnement) => {
      if (bezigeRij) return;
      setBezigeRij(abonnement.id);
      setFout(null);
      try {
        await deleteAbonnement(initiatiefId, abonnement.id);
        await laden();
      } catch {
        setFout(`Kon '${abonnement.term}' niet verwijderen.`);
      } finally {
        setBezigeRij(null);
      }
    },
    [bezigeRij, initiatiefId, laden],
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
            columns="minmax(160px,2fr) 90px 110px 120px 140px"
            sm-columns="1fr 70px 140px"
            md-columns="minmax(160px,2fr) 90px 110px 140px"
            accessible-label="Gevolgde zoektermen"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Term" />
              <nldd-text-cell text="Treffers" horizontal-alignment="right" />
              <nldd-text-cell
                text="Weggeklikt"
                horizontal-alignment="right"
                hide-below="md"
              />
              <nldd-text-cell text="Laatste" hide-below="lg" />
              <nldd-text-cell />
            </nldd-table-row>
            {abonnementen.map((a) => (
              <AbonnementRow
                key={a.id}
                abonnement={a}
                bezig={bezigeRij === a.id}
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
  bezig,
  onToggle,
  onDelete,
}: {
  abonnement: ParlementairAbonnement;
  bezig: boolean;
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
      />
      <nldd-text-cell
        text={String(abonnement.weggeklikt_totaal)}
        horizontal-alignment="right"
        hide-below="md"
      />
      <nldd-text-cell text={laatste} hide-below="lg" />
      <nldd-cell>
        <nldd-container layout="row" gap="4" horizontal-alignment="right">
          <nldd-button
            variant="neutral-transparent"
            size="xs"
            text={abonnement.actief ? 'Pauzeer' : 'Hervat'}
            disabled={orUndef(bezig)}
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
            disabled={orUndef(bezig)}
            accessible-label={`Verwijder ${abonnement.term}`}
            onClick={onDelete}
          />
        </nldd-container>
      </nldd-cell>
    </nldd-table-row>
  );
}
