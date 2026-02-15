import { BASE_URL, getCsrfToken } from '@/api/client';
import type { ImportResult, DatabaseBackupInfo, DatabaseRestoreResult, DatabaseResetResult } from '@/types';

export async function importPolitiekeInputs(file: File): Promise<ImportResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${BASE_URL}/api/import/politieke-inputs`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Import failed: ${response.statusText}`);
  }

  return response.json();
}

export async function importNodes(file: File): Promise<ImportResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${BASE_URL}/api/import/nodes`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Import failed: ${response.statusText}`);
  }

  return response.json();
}

export async function importEdges(file: File): Promise<ImportResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${BASE_URL}/api/import/edges`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Import failed: ${response.statusText}`);
  }

  return response.json();
}

export function exportNodesUrl(nodeType?: string): string {
  const params = nodeType ? `?node_type=${encodeURIComponent(nodeType)}` : '';
  return `${BASE_URL}/api/export/nodes${params}`;
}

export function exportEdgesUrl(): string {
  return `${BASE_URL}/api/export/edges`;
}

export function exportCorpusUrl(): string {
  return `${BASE_URL}/api/export/corpus`;
}

export function exportArchimateUrl(): string {
  return `${BASE_URL}/api/export/archimate`;
}

// ── Database backup / restore ──────────────────────────────────────

export async function exportDatabase(): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/admin/database/export`, {
    credentials: 'include',
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || `Export mislukt: ${response.statusText}`);
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename=(.+)/);
  const filename = match ? match[1] : 'bouwmeester-backup.tar.gz.age';
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function getDatabaseInfo(): Promise<DatabaseBackupInfo> {
  const response = await fetch(`${BASE_URL}/api/admin/database/info`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch database info: ${response.statusText}`);
  }
  return response.json();
}

export async function resetDatabase(confirm: string): Promise<DatabaseResetResult> {
  const response = await fetch(`${BASE_URL}/api/admin/database/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
    body: JSON.stringify({ confirm }),
    credentials: 'include',
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || `Reset mislukt: ${response.statusText}`);
  }

  return response.json();
}

export async function importDatabase(file: File): Promise<DatabaseRestoreResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${BASE_URL}/api/admin/database/import`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || `Import failed: ${response.statusText}`);
  }

  return response.json();
}
