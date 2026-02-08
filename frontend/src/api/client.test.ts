import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiError, apiGet, apiPost, apiPut, apiPatch, apiDelete } from './client';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, status = 200, statusText = 'OK') {
  return new Response(JSON.stringify(data), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  });
}

function emptyResponse(status = 204) {
  return new Response(null, { status, statusText: 'No Content' });
}

beforeEach(() => {
  mockFetch.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ApiError', () => {
  it('creates an error with status and body', () => {
    const err = new ApiError(404, 'Not Found', { detail: 'missing' });
    expect(err.status).toBe(404);
    expect(err.statusText).toBe('Not Found');
    expect(err.body).toEqual({ detail: 'missing' });
    expect(err.name).toBe('ApiError');
    expect(err.message).toContain('404');
  });
});

describe('apiGet', () => {
  it('fetches JSON data', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 1, name: 'test' }));

    const result = await apiGet<{ id: number; name: string }>('/api/items');

    expect(mockFetch).toHaveBeenCalledOnce();
    expect(result).toEqual({ id: 1, name: 'test' });
    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain('/api/items');
  });

  it('appends query params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]));

    await apiGet('/api/items', { status: 'active', limit: 10 });

    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain('status=active');
    expect(url).toContain('limit=10');
  });

  it('skips undefined params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]));

    await apiGet('/api/items', { status: undefined, limit: 5 });

    const url = mockFetch.mock.calls[0][0];
    expect(url).not.toContain('status');
    expect(url).toContain('limit=5');
  });

  it('throws ApiError on non-OK response', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Not found' }), {
        status: 404,
        statusText: 'Not Found',
      }),
    );

    await expect(apiGet('/api/items/999')).rejects.toThrow(ApiError);
  });
});

describe('apiPost', () => {
  it('sends JSON body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 1 }, 201, 'Created'));

    const result = await apiPost<{ id: number }>('/api/items', { name: 'new' });

    expect(result).toEqual({ id: 1 });
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({ name: 'new' });
  });
});

describe('apiPut', () => {
  it('sends PUT request', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 1, name: 'updated' }));

    const result = await apiPut('/api/items/1', { name: 'updated' });

    expect(result).toEqual({ id: 1, name: 'updated' });
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.method).toBe('PUT');
  });
});

describe('apiPatch', () => {
  it('sends PATCH request', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: 1, name: 'patched' }));

    const result = await apiPatch('/api/items/1', { name: 'patched' });

    expect(result).toEqual({ id: 1, name: 'patched' });
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.method).toBe('PATCH');
  });
});

describe('apiDelete', () => {
  it('handles 204 No Content', async () => {
    mockFetch.mockResolvedValueOnce(emptyResponse());

    const result = await apiDelete('/api/items/1');

    expect(result).toBeUndefined();
    const [, opts] = mockFetch.mock.calls[0];
    expect(opts.method).toBe('DELETE');
  });
});
