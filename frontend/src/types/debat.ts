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
  /** The sessie behind the channel: what stopping and resuming are asked for. */
  sessie_id: string | null;
  /** Where the timeline stands. `null` is a status too: not yet found on Debat Direct. */
  tijdlijn_status: TijdlijnStatus | null;
  /** Whether the bot follows this debate; `tijdlijn_status` alone cannot say, see above. */
  wordt_gevolgd: boolean;
}

export type TijdlijnStatus = 'gekoppeld' | 'loopt' | 'afgelopen' | 'afgelast';

/** Where a debate stands according to Debat Direct. */
export type DebatStand = 'niet_begonnen' | 'bezig' | 'geschorst' | 'afgelopen';

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
  /** `null` when Debat Direct does not know the debate, or could not be read. */
  stand: DebatStand | null;
  /** When it really started, once it has. */
  begonnen_om: string | null;
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

/** What stopping or resuming left behind. */
export interface DebatVolgenResult {
  sessie_id: string;
  tijdlijn_status: TijdlijnStatus | null;
  wordt_gevolgd: boolean;
}
