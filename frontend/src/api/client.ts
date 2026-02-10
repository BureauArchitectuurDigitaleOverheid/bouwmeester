function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)(?:__Host-)?bm_csrf=([^;]*)/);
  return match ? match[1] : '';
}

function getBaseUrl(): string {
  // Check runtime config (injected via config.js)
  const config = (window as unknown as Record<string, unknown>).__CONFIG__ as Record<string, string> | undefined;
  if (config?.BACKEND_URL) return config.BACKEND_URL;

  // Check build-time env
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL;

  // Auto-detect: if frontend runs on component-1, backend is on component-2
  const host = window.location.hostname;
  if (host.startsWith('component-1.')) {
    return `${window.location.protocol}//component-2.${host.slice('component-1.'.length)}`;
  }
  if (host.startsWith('component-1-')) {
    return `${window.location.protocol}//component-2-${host.slice('component-1-'.length)}`;
  }

  // Default: same origin (works with nginx proxy or Vite dev proxy)
  return '';
}

export const BASE_URL = getBaseUrl();

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown,
  ) {
    super(`API Error ${status}: ${statusText}`);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown;
    const text = await response.text();
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
    throw new ApiError(response.status, response.statusText, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

function buildUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.append(key, String(value));
      }
    });
  }
  return url.toString();
}

/** Headers for read-only requests. */
const readHeaders: HeadersInit = { 'Content-Type': 'application/json' };

/** Headers for state-changing requests (includes CSRF token). */
function mutationHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() };
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = buildUrl(path, params);
  const response = await fetch(url, {
    method: 'GET',
    headers: readHeaders,
    credentials: 'include',
  });
  return handleResponse<T>(response);
}

export async function apiPost<T>(path: string, data?: unknown): Promise<T> {
  const url = buildUrl(path);
  const response = await fetch(url, {
    method: 'POST',
    headers: mutationHeaders(),
    body: data ? JSON.stringify(data) : undefined,
    credentials: 'include',
  });
  return handleResponse<T>(response);
}

export async function apiPut<T>(path: string, data?: unknown): Promise<T> {
  const url = buildUrl(path);
  const response = await fetch(url, {
    method: 'PUT',
    headers: mutationHeaders(),
    body: data ? JSON.stringify(data) : undefined,
    credentials: 'include',
  });
  return handleResponse<T>(response);
}

export async function apiPatch<T>(path: string, data?: unknown): Promise<T> {
  const url = buildUrl(path);
  const response = await fetch(url, {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: data ? JSON.stringify(data) : undefined,
    credentials: 'include',
  });
  return handleResponse<T>(response);
}

export async function apiDelete<T = void>(path: string): Promise<T> {
  const url = buildUrl(path);
  const response = await fetch(url, {
    method: 'DELETE',
    headers: mutationHeaders(),
    credentials: 'include',
  });
  return handleResponse<T>(response);
}
