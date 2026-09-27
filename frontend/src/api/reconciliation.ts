import { apiGet, apiPost } from './client';

export interface ReconciliationItem {
  id: string;
  resource_type: string;
  handmatige_id: string;
  handmatige_naam: string | null;
  handmatige_afkorting: string | null;
  kandidaat_id: string | null;
  kandidaat_naam: string | null;
  kandidaat_bron: string;
  kandidaat_tooi_uri: string | null;
  match_reden: string;
  details: Record<string, unknown> | null;
  status: string;
  created_at: string;
}

/** Answer of both merges, with the trust the merge took away from the source. */
export interface MergeResult {
  status: string;
  doelrij_id: string;
  rewritten: Record<string, number>;
  eigenaarsrechten_verwijderd: number;
  plaatsingen_onbevestigd: number;
}

/** "Merge voltooid." plus what the merge took away, when anything. */
export function mergeResultMessage(result: MergeResult): string {
  const lost = [
    result.eigenaarsrechten_verwijderd > 0 && `${result.eigenaarsrechten_verwijderd} eigenaarsrechten verwijderd`,
    result.plaatsingen_onbevestigd > 0 && `${result.plaatsingen_onbevestigd} plaatsingen wachten op bevestiging`,
  ].filter(Boolean);
  return lost.length > 0 ? `Merge voltooid: ${lost.join(', ')}.` : 'Merge voltooid.';
}

export async function listReconciliations(
  status: 'open' | 'merged' | 'ignored' = 'open',
): Promise<ReconciliationItem[]> {
  return apiGet<ReconciliationItem[]>('/api/admin/reconciliation', { status });
}

export async function mergeReconciliation(id: string): Promise<MergeResult> {
  return apiPost(`/api/admin/reconciliation/${id}/merge`, {});
}

export async function ignoreReconciliation(id: string): Promise<{ status: string }> {
  return apiPost(`/api/admin/reconciliation/${id}/ignore`, {});
}

export interface OrphanScanResult {
  scanned: number;
  found_match: number;
  new_reconciliations: number;
  already_pending: number;
}

export async function scanOrphanHandmatig(): Promise<OrphanScanResult> {
  return apiPost('/api/admin/sync/orphan-handmatig', {});
}


export async function manualMerge(
  sourceId: string,
  targetId: string,
): Promise<MergeResult> {
  return apiPost('/api/admin/reconciliation/manual-merge', {
    source_id: sourceId,
    target_id: targetId,
  });
}
