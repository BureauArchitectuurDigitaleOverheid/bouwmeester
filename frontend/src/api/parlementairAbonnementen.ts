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
  /** Soorten kamerstukken waarvan deze term geen Mattermost-bericht geeft. */
  uitgezette_categorieen: string[] | null;
  /** Onder deze score (0-100) geen Mattermost-bericht; wel bewaard. */
  minimum_relevantie: number;
  /** Wanneer de eenmalige inhaalslag is gedaan; null = nog niet. */
  ingehaald_op: string | null;
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

/** Een voorgestelde zoekterm, met wat hij bij de bron oplevert. */
export interface Zoektermsuggestie {
  term: string;
  reden: string;
  soort: string;
  treffers: number;
  /** Documenten die de huidige termen nog niet vinden. Dit getal telt. */
  nieuwe_treffers: number;
  voorbeelden: string[];
}

export async function suggereerZoektermen(initiatiefId: string): Promise<Zoektermsuggestie[]> {
  return apiPost<Zoektermsuggestie[]>(`/api/initiatieven/${initiatiefId}/abonnementen/suggesties`);
}

/** Een Mattermost-kanaal dat aan dit initiatief hangt. */
export interface GekoppeldKanaal {
  id: string;
  channel_id: string;
  channel_name: string;
  channel_display_name: string;
}

/**
 * Waar de alerts van dit initiatief terechtkomen.
 *
 * Nul kanalen is een geldige uitkomst: de treffers staan dan alleen in de
 * webapp. Dat hoort de gebruiker te weten vóór hij zoektermen instelt,
 * anders belooft het scherm berichten die nergens aankomen.
 */
export async function getGekoppeldeKanalen(initiatiefId: string): Promise<GekoppeldKanaal[]> {
  return apiGet<GekoppeldKanaal[]>(`/api/initiatieven/${initiatiefId}/mattermost-channels`);
}
