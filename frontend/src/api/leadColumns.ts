import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { LeadColumn } from '@/types';

export interface LeadColumnCreate {
  name: string;
  color: string;
  is_active_stage?: boolean;
  is_public_visible?: boolean;
}

export interface LeadColumnUpdate {
  name?: string;
  color?: string;
  is_active_stage?: boolean;
  is_public_visible?: boolean;
}

export function listLeadColumns(initiatiefId: string): Promise<LeadColumn[]> {
  return apiGet(`/api/initiatieven/${initiatiefId}/columns`);
}

export function createLeadColumn(
  initiatiefId: string,
  data: LeadColumnCreate,
): Promise<LeadColumn> {
  return apiPost(`/api/initiatieven/${initiatiefId}/columns`, data);
}

export function updateLeadColumn(
  initiatiefId: string,
  columnId: string,
  data: LeadColumnUpdate,
): Promise<LeadColumn> {
  return apiPut(`/api/initiatieven/${initiatiefId}/columns/${columnId}`, data);
}

export function deleteLeadColumn(
  initiatiefId: string,
  columnId: string,
  moveTo?: string,
): Promise<void> {
  const qs = moveTo ? `?move_to=${encodeURIComponent(moveTo)}` : '';
  return apiDelete(
    `/api/initiatieven/${initiatiefId}/columns/${columnId}${qs}`,
  );
}

export function reorderLeadColumns(
  initiatiefId: string,
  columnIds: string[],
): Promise<LeadColumn[]> {
  return apiPost(`/api/initiatieven/${initiatiefId}/columns/reorder`, {
    column_ids: columnIds,
  });
}
