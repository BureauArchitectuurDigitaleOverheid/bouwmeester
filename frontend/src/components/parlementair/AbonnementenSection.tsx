import { useCallback, useEffect, useRef, useState } from 'react';
import { DetailSection } from '@/components/common/DetailSection';
import { eventValue, orUndef, useNlddEvent, useNlddValue } from '@/components/nldd/events';
import {
  createAbonnement,
  deleteAbonnement,
  getAbonnementen,
  getGekoppeldeKanalen,
  suggereerZoektermen,
  updateAbonnement,
  type GekoppeldKanaal,
  type ParlementairAbonnement,
  type Zoektermsuggestie,
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

  // Waar de alerts landen. Zonder gekoppeld kanaal blijven ze in de
  // webapp, en dat hoort zichtbaar te zijn vóór iemand zoektermen instelt.
  useEffect(() => {
    let actueel = true;
    getGekoppeldeKanalen(initiatiefId)
      .then((k) => actueel && setKanalen(k))
      .catch(() => actueel && setKanalen([]));
    return () => {
      actueel = false;
    };
  }, [initiatiefId]);

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
  const [kanalen, setKanalen] = useState<GekoppeldKanaal[] | null>(null);
  const [suggesties, setSuggesties] = useState<Zoektermsuggestie[] | null>(null);
  const [suggestiesBezig, setSuggestiesBezig] = useState(false);

  const haalSuggesties = useCallback(async () => {
    setSuggestiesBezig(true);
    setFout(null);
    try {
      setSuggesties(await suggereerZoektermen(initiatiefId));
    } catch {
      // De meting doet verzoeken aan een server van derden en een
      // LLM-call; als daar iets misgaat is dat geen reden om de rest van
      // het paneel onbruikbaar te maken.
      setFout('Kon geen suggesties ophalen.');
    } finally {
      setSuggestiesBezig(false);
    }
  }, [initiatiefId]);

  const voegSuggestieToe = useCallback(
    async (suggestie: Zoektermsuggestie) => {
      setFout(null);
      try {
        await createAbonnement(initiatiefId, { term: suggestie.term });
        setSuggesties((huidig) =>
          (huidig || []).filter((s) => s.term !== suggestie.term),
        );
        await laden();
      } catch {
        setFout(`Kon '${suggestie.term}' niet toevoegen.`);
      }
    },
    [initiatiefId, laden],
  );

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
          Nieuwe kamerstukken waarin een van deze termen voorkomt. Er wordt in de
          volledige tekst gezocht, dus ook in bijlagen en beslisnota&apos;s.
        </nldd-text>

        <Bezorging kanalen={kanalen} />

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
          {abonnementen.length > 0 && (
            <nldd-button
              variant="neutral-transparent"
              size="sm"
              text="Suggesties"
              start-icon="ai"
              loading={orUndef(suggestiesBezig)}
              onClick={haalSuggesties}
            />
          )}
        </nldd-container>

        {suggesties !== null && (
          <SuggestieLijst
            suggesties={suggesties}
            onToevoegen={voegSuggestieToe}
            onSluiten={() => setSuggesties(null)}
          />
        )}

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

/**
 * Waar de alerts van dit initiatief naartoe gaan.
 *
 * Dit stond eerst als belofte in de inleiding ("verschijnen in de
 * gekoppelde Mattermost-kanalen"), maar die kanalen kunnen er niet zijn.
 * Dan landen de treffers alleen in de webapp, en dat is iets anders dan
 * wat de tekst suggereerde.
 */
function Bezorging({ kanalen }: { kanalen: GekoppeldKanaal[] | null }) {
  if (kanalen === null) return null;

  if (kanalen.length === 0) {
    return (
      <nldd-banner
        variant="warning"
        size="sm"
        text="Dit initiatief heeft geen gekoppeld Mattermost-kanaal"
        supporting-text={
          'Treffers worden wel bewaard en zijn hier zichtbaar, maar er gaat ' +
          'geen bericht uit. Koppel een kanaal met /bouwmeester koppel ' +
          'initiatief <naam>.'
        }
      />
    );
  }

  const namen = kanalen
    .map((k) => `~${k.channel_name}`)
    .join(', ');
  return (
    <nldd-text size="xs" color="secondary">
      Berichten gaan naar {kanalen.length === 1 ? 'kanaal' : 'de kanalen'} {namen}.
    </nldd-text>
  );
}

/**
 * Voorgestelde zoektermen, met wat ze bij de bron opleveren.
 *
 * Het getal dat telt is `nieuwe_treffers`: een term die alleen dubbelt met
 * wat je al volgt voegt niets toe, hoeveel treffers hij ook heeft. Bij een
 * meting leverden vijf van de zes voorgestelde termen nul stukken op, dus
 * zonder deze getallen zou je vooral ruis aanzetten.
 */
function SuggestieLijst({
  suggesties,
  onToevoegen,
  onSluiten,
}: {
  suggesties: Zoektermsuggestie[];
  onToevoegen: (s: Zoektermsuggestie) => void;
  onSluiten: () => void;
}) {
  if (suggesties.length === 0) {
    return (
      <nldd-banner
        variant="neutral"
        size="sm"
        text="Geen aanvullende zoektermen gevonden."
        dismissible
      />
    );
  }

  return (
    <nldd-card>
      <nldd-container gap="8">
        <nldd-container layout="row" gap="8" vertical-alignment="center">
          <nldd-text size="xs" weight="bold">
            Voorgestelde zoektermen
          </nldd-text>
          <nldd-container width="fit-content" horizontal-alignment="right">
            <nldd-button
              variant="neutral-transparent"
              size="xs"
              text="Sluiten"
              onClick={onSluiten}
            />
          </nldd-container>
        </nldd-container>
        <nldd-text size="xs" color="secondary">
          Het aantal achter elke term is gemeten bij de bron. &quot;Nieuw&quot; telt
          alleen stukken die je huidige termen nog niet vinden.
        </nldd-text>
        {suggesties.map((s) => (
          <nldd-container key={s.term} layout="row" gap="8" vertical-alignment="center">
            <nldd-container gap="2">
              <nldd-container layout="row" gap="6" vertical-alignment="center">
                <nldd-text size="xs" weight="bold">
                  {s.term}
                </nldd-text>
                {s.nieuwe_treffers > 0 ? (
                  <nldd-tag
                    size="sm"
                    color="groen"
                    text={`${s.nieuwe_treffers} nieuw`}
                  />
                ) : (
                  <nldd-tag size="sm" color="neutral" text="geen nieuwe" />
                )}
                <nldd-text size="xs" color="secondary">
                  {s.treffers} treffers
                </nldd-text>
              </nldd-container>
              <nldd-text size="xs" color="secondary">
                {s.reden}
              </nldd-text>
            </nldd-container>
            <nldd-container width="fit-content" horizontal-alignment="right">
              <nldd-button
                variant="secondary"
                size="xs"
                text="Volgen"
                accessible-label={`Volg ${s.term}`}
                onClick={() => onToevoegen(s)}
              />
            </nldd-container>
          </nldd-container>
        ))}
      </nldd-container>
    </nldd-card>
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
