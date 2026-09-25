import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useEffect } from 'react';
import { render, act } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';

/**
 * The first auth check is what decides between the app and a full-screen
 * "Verbindingsfout". A backend that restarts during a deploy, or a laptop that
 * wakes before its Wi-Fi, makes that one request fail for a few seconds, and it
 * used to put the error screen up for good.
 */

const OK_BODY = { authenticated: true, oidc_configured: true, person: null };

function okResponse() {
  return new Response(JSON.stringify(OK_BODY), { status: 200 });
}

let seen: ReturnType<typeof useAuth> | null = null;
const record = (auth: ReturnType<typeof useAuth>) => {
  seen = auth;
};
function Probe() {
  const auth = useAuth();
  useEffect(() => record(auth));
  return null;
}

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('AuthProvider first status check', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    seen = null;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('waits out a short network outage instead of showing the error', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(okResponse());
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await flush();
    expect(seen?.loading).toBe(true);
    expect(seen?.error).toBeNull();

    await flush(1_000);
    await flush(2_000);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(seen?.loading).toBe(false);
    expect(seen?.error).toBeNull();
    expect(seen?.authenticated).toBe(true);
  });

  it('treats a 5xx as transient too', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('', { status: 503 }))
      .mockResolvedValueOnce(okResponse());
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await flush();
    await flush(1_000);

    expect(seen?.error).toBeNull();
    expect(seen?.authenticated).toBe(true);
  });

  it('does not retry a 4xx, which will not change by waiting', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 400 }));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(seen?.error).toMatch(/400/);
  });

  it('recovers from the error screen on its own once the backend is back', async () => {
    let up = false;
    const fetchMock = vi.fn(async () => {
      if (!up) throw new TypeError('Failed to fetch');
      return okResponse();
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    // Run through the whole backoff: 1 + 2 + 4 + 8 seconds.
    await flush();
    await flush(15_000);
    expect(seen?.error).toMatch(/niet bereikbaar/);

    up = true;
    await flush(10_000);

    expect(seen?.error).toBeNull();
    expect(seen?.authenticated).toBe(true);
  });
});
