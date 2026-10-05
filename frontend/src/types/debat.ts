/** A Mattermost team the bot is in. */
export interface DebatTeam {
  team_id: string;
  team_name: string | null;
  can_create_channel: boolean;
}

/** The channel that was set up for a debate, in one team. */
export interface DebatKanaal {
  team_id: string;
  channel_name: string;
  /** Missing when the team's url name could not be read from Mattermost. */
  channel_url: string | null;
}

export interface AankomendDebat {
  activiteit_id: string;
  nummer: string | null;
  soort: string | null;
  onderwerp: string;
  aanvang: string | null;
  einde: string | null;
  commissie: string | null;
  agenda_url: string | null;
  kanalen: DebatKanaal[];
}

export interface AankomendeDebatten {
  debatten: AankomendDebat[];
  teams: DebatTeam[];
  /** Why there are no teams, when Mattermost could not be asked. */
  mattermost_melding: string | null;
}

export type DebatStartOutcome = 'created' | 'exists' | 'in_progress' | 'refused' | 'failed';

export interface DebatStartResult {
  outcome: DebatStartOutcome;
  /** For refused and failed: the reason, to show as is. */
  melding: string | null;
  kanaal: DebatKanaal | null;
}
