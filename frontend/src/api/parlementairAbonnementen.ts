import { apiGet, apiPost, apiPatch, apiDelete } from './client';

/** Een zoekterm die een initiatief volgt in nieuwe kamerstukken. */
export interface ParlementairAbonnement {
  id: string;
  scope_type: string;
  scope_id: string;
  term: string;
  is_frase: boolean;
  actief: boolean;
  laatste_treffer_op: string | null;
  /** Opgeteld over alle rondes; loopt uiteen met `treffers` als items zijn verwijderd. */
  treffers_totaal: number;
  /** Hoe vaak een treffer van deze term als niet-relevant is gemarkeerd. */
  weggeklikt_totaal: number;
  notitie: string | null;
  created_by_id: string | null;
  created_at: string;
  /** Aantal kamerstukken dat er nu aan hangt. */
  treffers: number;
}

export interface AbonnementCreate {
  term: string;
  is_frase?: boolean;
  notitie?: string | null;
}

export async function getAbonnementen(initiatiefId: string): Promise<ParlementairAbonnement[]> {
  return apiGet<ParlementairAbonnement[]>(`/api/initiatieven/${initiatiefId}/abonnementen`);
}

export async function createAbonnement(
  initiatiefId: string,
  data: AbonnementCreate,
): Promise<ParlementairAbonnement> {
  return apiPost<ParlementairAbonnement>(`/api/initiatieven/${initiatiefId}/abonnementen`, data);
}

export async function updateAbonnement(
  initiatiefId: string,
  abonnementId: string,
  data: { actief?: boolean; notitie?: string | null },
): Promise<ParlementairAbonnement> {
  return apiPatch<ParlementairAbonnement>(
    `/api/initiatieven/${initiatiefId}/abonnementen/${abonnementId}`,
    data,
  );
}

export async function deleteAbonnement(initiatiefId: string, abonnementId: string): Promise<void> {
  return apiDelete(`/api/initiatieven/${initiatiefId}/abonnementen/${abonnementId}`);
}
