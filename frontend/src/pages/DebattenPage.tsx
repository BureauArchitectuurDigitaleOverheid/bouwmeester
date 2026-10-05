import { Fragment, useCallback, useMemo, useRef, useState } from 'react';
import { useAankomendeDebatten, useStartDebat } from '@/hooks/useDebatten';
import { useToast } from '@/contexts/ToastContext';
import { EmptyState } from '@/components/common/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { Select } from '@/components/common/Select';
import { NlddButton } from '@/components/nldd/NlddButton';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import type { AankomendDebat, DebatKanaal } from '@/types/debat';
import {
  filterDebatten,
  formatRegel,
  groepeerPerDag,
  bewaarGekozenTeam,
  kiesTeam,
  leesGekozenTeam,
  zichtbareKanalen,
  startMelding,
} from './debatten';

/** `nldd-search-field` with its `input` event bridged to React. */
function DebatSearchField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return (
    <nldd-search-field
      ref={ref}
      value={value}
      placeholder="Zoek op onderwerp of commissie..."
      accessible-label="Zoek in komende debatten"
    />
  );
}

function KanaalLink({ kanaal }: { kanaal: DebatKanaal }) {
  const naam = `~${kanaal.channel_name}`;
  // Without the team's url name there is nothing to link to; the name alone
  // still tells which channel to look for.
  return kanaal.channel_url ? (
    <nldd-link href={kanaal.channel_url} target="_blank" text={naam} />
  ) : (
    <nldd-text size="sm" color="secondary">{naam}</nldd-text>
  );
}

interface DebatRowProps {
  debat: AankomendDebat;
  teamId: string | null;
  canStart: boolean;
  pending: boolean;
  busy: boolean;
  onStart: (debat: AankomendDebat) => void;
}

function DebatRow({ debat, teamId, canStart, pending, busy, onStart }: DebatRowProps) {
  const kanalen = zichtbareKanalen(debat, teamId);
  return (
    <nldd-list-item>
      <nldd-text-cell text={debat.onderwerp} supporting-text={formatRegel(debat)} />
      {/* One cell per thing on the right, not a row container inside a cell:
          a cell is as wide as its content and a container as wide as its
          cell, so the two measure each other and both end at zero. Cells sit
          flush against each other, so the room between them is a spacer
          cell. */}
      {debat.agenda_url && (
        <nldd-cell horizontal-alignment="right">
          <nldd-link
            href={debat.agenda_url}
            target="_blank"
            text="Agenda"
            accessible-label={`Agenda van ${debat.onderwerp}`}
          />
        </nldd-cell>
      )}
      {kanalen.map((kanaal) => (
        <Fragment key={kanaal.team_id}>
          <nldd-spacer-cell size="16" />
          <nldd-cell horizontal-alignment="right">
            <KanaalLink kanaal={kanaal} />
          </nldd-cell>
        </Fragment>
      ))}
      {kanalen.length === 0 && canStart && (
        <>
          <nldd-spacer-cell size="16" />
          <nldd-cell horizontal-alignment="right">
            <NlddButton
              variant="secondary"
              size="sm"
              startIcon="microphone"
              text="Kanaal opzetten"
              accessibleLabel={`Kanaal opzetten voor ${debat.onderwerp}`}
              loading={pending}
              disabled={busy}
              onClick={() => onStart(debat)}
            />
          </nldd-cell>
        </>
      )}
    </nldd-list-item>
  );
}

export function DebattenPage() {
  const { data, isLoading } = useAankomendeDebatten();
  const start = useStartDebat();
  const { showSuccess, showError } = useToast();
  const [search, setSearch] = useState('');
  const [chosenTeam, setChosenTeam] = useState<string | null>(leesGekozenTeam);

  const teams = useMemo(() => data?.teams ?? [], [data]);
  const team = kiesTeam(teams, chosenTeam);
  const teamId = team?.team_id ?? null;
  // No permission check here, like the Kamerstukken page: the frontend only
  // knows permissions once a person is resolved, and the backend refuses a
  // start that is not allowed.
  const canStart = team?.can_create_channel ?? false;

  const dagen = useMemo(
    () => groepeerPerDag(filterDebatten(data?.debatten ?? [], search)),
    [data, search],
  );

  const handleStart = useCallback(
    (debat: AankomendDebat) => {
      if (!teamId) return;
      start.mutate(
        { activiteitId: debat.activiteit_id, teamId },
        {
          onSuccess: (result) => {
            const { tekst, fout } = startMelding(result, team?.team_name);
            (fout ? showError : showSuccess)(tekst);
          },
        },
      );
    },
    [start, teamId, team, showError, showSuccess],
  );

  // Only without data. A refetch that fails in the background (after a
  // start, or when the window gets focus) must not wipe a list that is there.
  if (!data) {
    if (isLoading) return <LoadingSpinner padding="64" />;
    return (
      <EmptyState
        title="De agenda is nu niet op te halen"
        description="Probeer het over een paar minuten opnieuw."
      />
    );
  }

  const handleTeam = (teamId: string) => {
    setChosenTeam(teamId);
    bewaarGekozenTeam(teamId);
  };

  const melding =
    data.mattermost_melding ??
    (team && !team.can_create_channel
      ? 'De bot mag in dit team geen kanalen aanmaken. Een Mattermost-beheerder kan dat aanzetten.'
      : null);
  // Several teams and none chosen: say so, instead of a page without buttons.
  const kiesEerst = !data.mattermost_melding && teams.length > 1 && team === null;

  return (
    <nldd-container gap="24">
      <nldd-toolbar label="Debatten filteren">
        <nldd-toolbar-item slot="start" priority={1} min-width="60%">
          {/* Bottom-aligned, each field in a fixed-width container: the team
              field carries a label above it and the search field does not, so
              centring would put them at different heights. A labelled Select
              is a form field that takes the full width it is given; without
              the container it drops onto a line of its own. */}
          <nldd-container layout="wrap" gap="12" vertical-alignment="bottom">
            <nldd-container width="320px">
              <DebatSearchField value={search} onChange={setSearch} />
            </nldd-container>
            {teams.length > 1 && (
              <nldd-container width="256px">
                <Select
                  label="Kanaal komt in team"
                  placeholder="Kies een team"
                  // The choice is needed before anything can be started, and
                  // without `required` the field labels itself "Optioneel".
                  required
                  value={teamId ?? ''}
                  onChange={(e) => handleTeam(e.target.value)}
                  options={teams.map((t) => ({ value: t.team_id, label: t.team_name ?? t.team_id }))}
                />
              </nldd-container>
            )}
          </nldd-container>
        </nldd-toolbar-item>
      </nldd-toolbar>

      {melding && (
        <nldd-text size="sm" color="secondary">
          {melding} Kanalen opzetten kan hier nu niet; de agenda hieronder klopt wel.
        </nldd-text>
      )}

      {kiesEerst && (
        <nldd-text size="sm" color="secondary">
          Kies hierboven eerst het Mattermost-team waar het kanaal in moet komen. Daarna
          verschijnt per vergadering de knop om een kanaal op te zetten.
        </nldd-text>
      )}

      {dagen.length === 0 ? (
        <EmptyState
          title="Geen debatten gevonden"
          description={
            search
              ? 'Geen komende vergadering past bij deze zoekterm.'
              : 'Er staan de komende weken geen openbare vergaderingen op de agenda.'
          }
        />
      ) : (
        dagen.map((dag) => (
          <nldd-container key={dag.key} gap="8">
            <nldd-title size={6}><h2>{dag.label}</h2></nldd-title>
            <nldd-list variant="box-tinted" dividers="always" accessible-label={`Debatten op ${dag.label}`}>
              {dag.debatten.map((debat) => (
                <DebatRow
                  key={debat.activiteit_id}
                  debat={debat}
                  teamId={teamId}
                  canStart={canStart}
                  pending={start.isPending && start.variables?.activiteitId === debat.activiteit_id}
                  busy={start.isPending}
                  onStart={handleStart}
                />
              ))}
            </nldd-list>
          </nldd-container>
        ))
      )}
    </nldd-container>
  );
}
