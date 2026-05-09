import { apiGet, apiPost } from './client';

export interface SyncStatus {
  laatste_run_per_bron: Record<string, string>;
  actief_per_bron: Record<string, number>;
  open_reconciliations: number;
}

export async function getSyncStatus(): Promise<SyncStatus> {
  return apiGet<SyncStatus>('/api/admin/sync/status');
}

export type SyncEndpoint =
  | 'tooi'
  | 'ministeries-csv'
  | 'rio'
  | 'organogram'
  | 'tk-personen'
  | 'kabinet'
  | 'abd'
  | 'historische-kabinetten'
  | 'onderwijsinstellingen'
  | 'wikidata-qid';

export async function triggerSync(endpoint: SyncEndpoint): Promise<unknown> {
  return apiPost(`/api/admin/sync/${endpoint}`, {});
}

export async function triggerAllSyncs(): Promise<unknown> {
  return apiPost('/api/admin/sync/all', {});
}

export interface SyncLogEntry {
  id: string;
  sync_run_id: string;
  bron: string;
  action: string;
  tooi_uri: string | null;
  organisatie_eenheid_id: string | null;
  person_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  note: string | null;
  created_at: string;
}

export async function getSyncLog(
  bron?: string,
  limit = 50,
): Promise<SyncLogEntry[]> {
  const params: Record<string, string> = { limit: String(limit) };
  if (bron) params.bron = bron;
  return apiGet<SyncLogEntry[]>('/api/admin/sync/log', params);
}

export const SYNC_LABELS: Record<SyncEndpoint, string> = {
  'tooi': 'TOOI-waardelijsten',
  'ministeries-csv': 'Ministeries CSV (OIN/FTE)',
  'rio': 'RIO email-domeinen',
  'organogram': 'Organogram-scrape (DG/directie)',
  'tk-personen': 'Tweede + Eerste Kamer',
  'kabinet': 'Kabinet (rijksoverheid.nl)',
  'abd': 'ABD-benoemingen (Playwright)',
  'historische-kabinetten': 'Historische kabinetten',
  'onderwijsinstellingen': 'Onderwijsinstellingen',
  'wikidata-qid': 'Wikidata QID-koppeling',
};
