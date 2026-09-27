import type { Mock } from 'vitest';

/** One evaluation as it goes over the wire to `POST /api/authz/evaluations`. */
export interface Question {
  action: string;
  resource: { type: string; id?: string; properties?: Record<string, unknown> };
}

interface FakeBackend {
  /** The decision for each evaluation; default: refuse. */
  decide?: (q: Question) => boolean;
  /** `GET /api/authz/eenheden?action=...`; default: none. */
  eenheden?: (action: string) => { all: boolean; ids: string[] };
  /** Any other request: the JSON to answer with; default `[]`. */
  get?: (url: string) => unknown;
}

const json = (data: unknown) =>
  new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });

/** Answer `fetch` like the backend's authz endpoints, and `get` for the rest. */
export function fakeBackend(fetchMock: Mock, { decide = () => false, eenheden, get }: FakeBackend) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.includes('/api/authz/evaluations')) {
      const body = JSON.parse(String(init?.body)) as { evaluations: Question[] };
      return json({ evaluations: body.evaluations.map((q) => ({ decision: decide(q) })) });
    }
    if (url.includes('/api/authz/eenheden')) {
      const action = new URL(url, 'http://localhost').searchParams.get('action') ?? '';
      return json(eenheden ? eenheden(action) : { all: false, ids: [] });
    }
    return json(get ? get(url) : []);
  });
}

/** Every evaluation the frontend asked, over all requests. */
export function askedQuestions(fetchMock: Mock): Question[] {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).includes('/api/authz/evaluations'))
    .flatMap(([, init]) => (JSON.parse(String((init as RequestInit).body)) as { evaluations: Question[] }).evaluations);
}
