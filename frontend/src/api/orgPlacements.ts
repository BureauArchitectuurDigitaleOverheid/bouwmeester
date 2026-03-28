import { apiGet, apiPost } from './client';

export interface OrgPlacementRequest {
  id: string;
  person_id: string;
  person_naam: string;
  organisatie_eenheid_id: string;
  eenheid_naam: string;
  dienstverband: string;
  status: 'pending' | 'approved' | 'denied';
  requested_at: string;
  decided_at: string | null;
  decided_by: string | null;
}

export interface CreatePlacementRequest {
  organisatie_eenheid_id: string;
  dienstverband?: string;
}

export function requestPlacement(data: CreatePlacementRequest) {
  return apiPost<OrgPlacementRequest>('/api/org-placements/request', data);
}

export function getPendingPlacements() {
  return apiGet<OrgPlacementRequest[]>('/api/org-placements/pending');
}

export function getMyPlacementRequests() {
  return apiGet<OrgPlacementRequest[]>('/api/org-placements/my-requests');
}

export function approvePlacement(id: string) {
  return apiPost<OrgPlacementRequest>(`/api/org-placements/${id}/approve`);
}

export function denyPlacement(id: string) {
  return apiPost<OrgPlacementRequest>(`/api/org-placements/${id}/deny`);
}
