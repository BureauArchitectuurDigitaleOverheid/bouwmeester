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

export async function listReconciliations(
  status: 'open' | 'merged' | 'ignored' = 'open',
): Promise<ReconciliationItem[]> {
  return apiGet<ReconciliationItem[]>('/api/admin/reconciliation', { status });
}

export async function mergeReconciliation(id: string): Promise<{ status: string; doelrij_id: string }> {
  return apiPost(`/api/admin/reconciliation/${id}/merge`, {});
}

export async function ignoreReconciliation(id: string): Promise<{ status: string }> {
  return apiPost(`/api/admin/reconciliation/${id}/ignore`, {});
}
