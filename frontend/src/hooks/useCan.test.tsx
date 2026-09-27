import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { createAuthzBatcher, evaluate, MAX_EVALUATIONS } from '@/api/authz';
import { apiPost } from '@/api/client';
import { CHANGES_RIGHTS, syncAuthzDecisions, touches, useCan, useEenhedenWith } from './useCan';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

/** Answer every evaluation POST with `decision` for each question asked. */
function answerAll(decision: (action: string) => boolean) {
  mockFetch.mockImplementation(async (_url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body)) as { evaluations: { action: string }[] };
    return new Response(
      JSON.stringify({ evaluations: body.evaluations.map((e) => ({ decision: decision(e.action) })) }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
  });
}

function sentBodies() {
  return mockFetch.mock.calls.map(
    ([, init]) => JSON.parse(String((init as RequestInit).body)) as { evaluations: unknown[] },
  );
}

function wrapperFor(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe('authz batcher', () => {
  it('sends everything asked in one tick as a single POST, answers in order', async () => {
    answerAll((action) => action === 'node:update');
    const decide = createAuthzBatcher();

    const answers = await Promise.all([
      decide({ action: 'node:update', resource: { type: 'corpus_node', id: 'n1' } }),
      decide({ action: 'node:delete', resource: { type: 'corpus_node', id: 'n1' } }),
      decide({ action: 'task:create', resource: { type: 'task', eenheidId: 'e1' } }),
    ]);

    expect(answers).toEqual([true, false, false]);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toContain('/api/authz/evaluations');
    expect(sentBodies()[0]).toEqual({
      evaluations: [
        { action: 'node:update', resource: { type: 'corpus_node', id: 'n1' } },
        { action: 'node:delete', resource: { type: 'corpus_node', id: 'n1' } },
        { action: 'task:create', resource: { type: 'task', properties: { eenheid_id: 'e1' } } },
      ],
    });
  });

  it('sends grant and anywhere questions with backend property names', async () => {
    answerAll(() => true);
    const decide = createAuthzBatcher();

    await Promise.all([
      decide({ action: 'task:create', resource: { type: 'task', anywhere: true } }),
      decide({
        action: 'resource_role:grant',
        resource: { type: 'lead', id: 'l1', rol: 'opdrachtgever', targetPersonId: 'p1' },
      }),
      decide({ action: 'role:assign', resource: { type: 'role', roleId: 'editor', eenheidId: 'e1' } }),
    ]);

    expect(sentBodies()[0]).toEqual({
      evaluations: [
        { action: 'task:create', resource: { type: 'task', properties: { anywhere: true } } },
        {
          action: 'resource_role:grant',
          resource: { type: 'lead', id: 'l1', properties: { rol: 'opdrachtgever', target_person_id: 'p1' } },
        },
        {
          action: 'role:assign',
          resource: { type: 'role', properties: { eenheid_id: 'e1', role_id: 'editor' } },
        },
      ],
    });
  });

  it('sends revoke, assign-anywhere and placement questions with backend property names', async () => {
    answerAll(() => true);
    const decide = createAuthzBatcher();

    await Promise.all([
      decide({
        action: 'resource_role:revoke',
        resource: { type: 'initiatief', id: 'i1', rol: 'eigenaar', targetPersonId: 'p1' },
      }),
      decide({ action: 'role:assign', resource: { type: 'role', anywhere: true, targetPersonId: 'p1' } }),
      decide({ action: 'person:place', resource: { type: 'person', eenheidId: 'e1', contact: true } }),
      decide({ action: 'person:place', resource: { type: 'person', id: 'p1', eenheidId: 'e1', ending: true } }),
    ]);

    expect(sentBodies()[0]).toEqual({
      evaluations: [
        {
          action: 'resource_role:revoke',
          resource: { type: 'initiatief', id: 'i1', properties: { rol: 'eigenaar', target_person_id: 'p1' } },
        },
        { action: 'role:assign', resource: { type: 'role', properties: { anywhere: true, target_person_id: 'p1' } } },
        { action: 'person:place', resource: { type: 'person', properties: { eenheid_id: 'e1', contact: true } } },
        {
          action: 'person:place',
          resource: { type: 'person', id: 'p1', properties: { eenheid_id: 'e1', ending: true } },
        },
      ],
    });
  });

  it('starts a new request for questions asked after the previous tick', async () => {
    answerAll(() => true);
    const decide = createAuthzBatcher();

    await decide({ action: 'node:update', resource: { type: 'corpus_node', id: 'a' } });
    await decide({ action: 'node:update', resource: { type: 'corpus_node', id: 'b' } });

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('chunks at the backend limit and keeps the order across chunks', async () => {
    // Allow only the even-numbered nodes, so order mistakes show up.
    mockFetch.mockImplementation(async (_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body)) as { evaluations: { resource: { id: string } }[] };
      return new Response(
        JSON.stringify({
          evaluations: body.evaluations.map((e) => ({ decision: Number(e.resource.id) % 2 === 0 })),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    });
    const total = MAX_EVALUATIONS * 2 + 10;
    const questions = Array.from({ length: total }, (_, i) => ({
      action: 'node:update',
      resource: { type: 'corpus_node' as const, id: String(i) },
    }));

    const answers = await evaluate(questions);

    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(sentBodies().map((b) => b.evaluations.length)).toEqual([50, 50, 10]);
    expect(answers).toEqual(questions.map((_, i) => ({ ok: true, decision: i % 2 === 0 })));
  });

  it('fails only the questions of a failed chunk', async () => {
    let call = 0;
    mockFetch.mockImplementation(async (_url: string, init: RequestInit) => {
      call += 1;
      if (call === 2) return new Response('boom', { status: 502 });
      const body = JSON.parse(String(init.body)) as { evaluations: unknown[] };
      return new Response(JSON.stringify({ evaluations: body.evaluations.map(() => ({ decision: true })) }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    const decide = createAuthzBatcher();
    const questions = Array.from({ length: MAX_EVALUATIONS + 1 }, (_, i) =>
      decide({ action: 'node:update', resource: { type: 'corpus_node', id: String(i) } }),
    );

    const results = await Promise.allSettled(questions);

    expect(results.slice(0, MAX_EVALUATIONS).every((r) => r.status === 'fulfilled' && r.value)).toBe(true);
    expect(results[MAX_EVALUATIONS].status).toBe('rejected');
  });

  it('rejects every waiting question when the request fails', async () => {
    mockFetch.mockResolvedValue(new Response('boom', { status: 500 }));
    const decide = createAuthzBatcher();

    const results = await Promise.allSettled([
      decide({ action: 'node:update', resource: { type: 'corpus_node', id: 'x' } }),
      decide({ action: 'node:delete', resource: { type: 'corpus_node', id: 'x' } }),
    ]);

    expect(results.map((r) => r.status)).toEqual(['rejected', 'rejected']);
  });
});

describe('useCan', () => {
  function newClient() {
    return new QueryClient({ defaultOptions: { queries: { retry: false } } });
  }

  it('batches the decisions of components rendered together into one POST', async () => {
    answerAll((action) => action !== 'node:delete');
    const client = newClient();
    function Probe({ action }: { action: string }) {
      const { allowed } = useCan(action, { type: 'corpus_node', id: 'n1' });
      return <span data-action={action}>{String(allowed)}</span>;
    }
    const seen = (action: string) => container.querySelector(`[data-action="${action}"]`)?.textContent;

    const { container } = render(
      <QueryClientProvider client={client}>
        <Probe action="node:update" />
        <Probe action="node:delete" />
        <Probe action="edge:create" />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(seen('node:update')).toBe('true'));
    expect(seen('node:delete')).toBe('false');
    expect(seen('edge:create')).toBe('true');
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(sentBodies()[0].evaluations).toHaveLength(3);
  });

  it('is not allowed while loading, and serves a repeat question from the cache', async () => {
    answerAll(() => true);
    const client = newClient();
    const resource = { type: 'task', id: 't1' } as const;

    const first = renderHook(() => useCan('task:update', resource), { wrapper: wrapperFor(client) });
    expect(first.result.current).toMatchObject({ allowed: false, isLoading: true, showAction: false });
    await waitFor(() => expect(first.result.current.allowed).toBe(true));

    const second = renderHook(() => useCan('task:update', resource), { wrapper: wrapperFor(client) });
    expect(second.result.current).toMatchObject({ allowed: true, isLoading: false });
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('asks nothing without a resource', () => {
    const client = newClient();
    const { result } = renderHook(() => useCan('task:update', null), { wrapper: wrapperFor(client) });
    expect(result.current.allowed).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('reports a failed decision as an error, not as a refusal', async () => {
    mockFetch.mockImplementation(async () => new Response('boom', { status: 500 }));
    const client = newClient();
    const { result } = renderHook(() => useCan('node:update', { type: 'corpus_node', id: 'n1' }), {
      wrapper: wrapperFor(client),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.allowed).toBe(false);
    // A primary action stays on screen, disabled.
    expect(result.current.showAction).toBe(true);
  });

  describe('after writes', () => {
    let allowed: boolean;
    let stop: () => void;
    let client: QueryClient;

    beforeEach(() => {
      allowed = false;
      answerAll(() => allowed);
      client = newClient();
      stop = syncAuthzDecisions(client);
      return () => stop();
    });

    // Two decisions about two leads, and a write that touches whatever `meta` says.
    function renderDecisions(meta?: Parameters<typeof useMutation>[0]['meta']) {
      const view = renderHook(
        () => ({
          l1: useCan('lead:update', { type: 'lead', id: 'l1' }),
          l2: useCan('lead:update', { type: 'lead', id: 'l2' }),
          write: useMutation({ mutationFn: async (_: { id: string }) => 'ok', meta }),
        }),
        { wrapper: wrapperFor(client) },
      );
      return view.result;
    }

    async function loaded(result: { current: { l1: { isLoading: boolean }; l2: { isLoading: boolean } } }) {
      await waitFor(() => expect(result.current.l1.isLoading || result.current.l2.isLoading).toBe(false));
    }

    it('asks again only about the resource a mutation touched', async () => {
      const result = renderDecisions(touches(({ id }: { id: string }) => ({ type: 'lead', id })));
      await loaded(result);

      allowed = true;
      await act(() => result.current.write.mutateAsync({ id: 'l1' }));

      await waitFor(() => expect(result.current.l1.allowed).toBe(true));
      expect(result.current.l2.allowed).toBe(false);
      expect(mockFetch).toHaveBeenCalledTimes(2);
      expect(sentBodies()[1].evaluations).toHaveLength(1);
    });

    it('asks everything again after a change to who has access', async () => {
      const result = renderDecisions(CHANGES_RIGHTS);
      await loaded(result);

      allowed = true;
      await act(() => result.current.write.mutateAsync({ id: 'x' }));

      await waitFor(() => expect(result.current.l1.allowed && result.current.l2.allowed).toBe(true));
    });

    it('asks nothing again after a write without an authz effect', async () => {
      const result = renderDecisions();
      await loaded(result);

      allowed = true;
      await act(() => result.current.write.mutateAsync({ id: 'l1' }));

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(result.current.l1.allowed).toBe(false);
    });

    it('asks everything again after any 403', async () => {
      const result = renderDecisions();
      await loaded(result);

      allowed = true;
      mockFetch.mockResolvedValueOnce(new Response('{"detail":"nee"}', { status: 403 }));
      await expect(apiPost('/api/leads/l1/contacts')).rejects.toThrow();

      await waitFor(() => expect(result.current.l1.allowed && result.current.l2.allowed).toBe(true));
    });
  });
});

describe('useEenhedenWith', () => {
  let answer: { all: boolean; ids: string[] };
  let client: QueryClient;

  beforeEach(() => {
    answer = { all: false, ids: ['e1'] };
    mockFetch.mockImplementation(
      async () => new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });

  const requestedUrls = () => mockFetch.mock.calls.map(([url]) => String(url));

  it('asks the whole list in one GET and answers per eenheid', async () => {
    const { result } = renderHook(() => useEenhedenWith('org:manage'), { wrapper: wrapperFor(client) });

    expect(result.current.includes('e1')).toBe(false);
    await waitFor(() => expect(result.current.includes('e1')).toBe(true));
    expect(result.current.includes('e2')).toBe(false);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(requestedUrls()[0]).toContain('/api/authz/eenheden?action=org%3Amanage');
  });

  it('treats `all` as every eenheid', async () => {
    answer = { all: true, ids: [] };
    const { result } = renderHook(() => useEenhedenWith('org:manage'), { wrapper: wrapperFor(client) });

    await waitFor(() => expect(result.current.includes('anything')).toBe(true));
  });

  it('asks again after a change to who has access', async () => {
    const stop = syncAuthzDecisions(client);
    const { result } = renderHook(
      () => ({
        eenheden: useEenhedenWith('org:manage'),
        write: useMutation({ mutationFn: async () => 'ok', meta: CHANGES_RIGHTS }),
      }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => expect(result.current.eenheden.includes('e1')).toBe(true));

    answer = { all: false, ids: ['e2'] };
    await act(() => result.current.write.mutateAsync());

    await waitFor(() => expect(result.current.eenheden.includes('e2')).toBe(true));
    expect(result.current.eenheden.includes('e1')).toBe(false);
    stop();
  });
});
