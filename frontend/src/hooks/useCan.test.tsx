import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { createAuthzBatcher, evaluate, MAX_EVALUATIONS } from '@/api/authz';
import { refreshAuthzOnMutation, useCan } from './useCan';

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
    expect(answers).toEqual(questions.map((_, i) => i % 2 === 0));
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
    expect(first.result.current).toEqual({ allowed: false, isLoading: true });
    await waitFor(() => expect(first.result.current.allowed).toBe(true));

    const second = renderHook(() => useCan('task:update', resource), { wrapper: wrapperFor(client) });
    expect(second.result.current).toEqual({ allowed: true, isLoading: false });
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('asks nothing without a resource', () => {
    const client = newClient();
    const { result } = renderHook(() => useCan('task:update', null), { wrapper: wrapperFor(client) });
    expect(result.current.allowed).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('asks again after a successful mutation', async () => {
    let allowed = false;
    answerAll(() => allowed);
    const client = newClient();
    const stop = refreshAuthzOnMutation(client);
    const { result } = renderHook(
      () => ({
        can: useCan('lead:update', { type: 'lead', id: 'l1' }),
        grant: useMutation({ mutationFn: async () => 'ok' }),
      }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => expect(result.current.can.isLoading).toBe(false));
    expect(result.current.can.allowed).toBe(false);

    // Say the mutation made the user a member: the next answer is yes.
    allowed = true;
    await act(() => result.current.grant.mutateAsync());

    await waitFor(() => expect(result.current.can.allowed).toBe(true));
    expect(mockFetch).toHaveBeenCalledTimes(2);
    stop();
  });
});
