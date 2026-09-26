import { apiPost } from './client';

/** Resource types the backend decision point (`core/authz.py`) knows. */
export type AuthzResourceType =
  | 'corpus_node'
  | 'edge'
  | 'task'
  | 'lead'
  | 'initiatief'
  | 'opdracht'
  | 'organisatie_eenheid'
  | 'tag'
  | 'samenwerkingsverband'
  | 'person'
  | 'initiatief_update'
  | 'lead_column'
  | 'lead_update'
  | 'lead_activity'
  | 'lead_attachment'
  | 'parlementair_abonnement'
  | 'mattermost_channel_link'
  | 'github_link'
  | 'stakeholder_assessment';

/**
 * What an action is about: an existing resource (`id`), or one about to be
 * created, optionally in a given eenheid (`eenheidId`).
 */
export interface AuthzResource {
  type: AuthzResourceType;
  id?: string;
  eenheidId?: string;
}

export interface AuthzEvaluation {
  /** A permission string such as `node:update` or `lead_column:create`. */
  action: string;
  resource: AuthzResource;
}

interface EvaluationsResponse {
  evaluations: { decision: boolean }[];
}

/** The backend accepts at most this many evaluations per request. */
export const MAX_EVALUATIONS = 50;

function toWire({ action, resource }: AuthzEvaluation) {
  return {
    action,
    resource: {
      type: resource.type,
      ...(resource.id ? { id: resource.id } : {}),
      ...(resource.eenheidId ? { properties: { eenheid_id: resource.eenheidId } } : {}),
    },
  };
}

/** Ask the backend for decisions, in order; chunked to the request limit. */
export async function evaluate(evaluations: AuthzEvaluation[]): Promise<boolean[]> {
  const chunks: AuthzEvaluation[][] = [];
  for (let i = 0; i < evaluations.length; i += MAX_EVALUATIONS) {
    chunks.push(evaluations.slice(i, i + MAX_EVALUATIONS));
  }
  const responses = await Promise.all(
    chunks.map((chunk) =>
      apiPost<EvaluationsResponse>('/api/authz/evaluations', {
        evaluations: chunk.map(toWire),
      }),
    ),
  );
  return responses.flatMap((r) => r.evaluations.map((e) => e.decision));
}

interface Pending {
  evaluation: AuthzEvaluation;
  resolve: (decision: boolean) => void;
  reject: (error: unknown) => void;
}

/**
 * Collect every evaluation asked for in the same tick into one request.
 *
 * Components mounting together each ask their own question; this turns a
 * detail view with ten buttons into a single POST instead of ten.
 */
export function createAuthzBatcher(send: typeof evaluate = evaluate) {
  let queue: Pending[] = [];

  function flush() {
    const batch = queue;
    queue = [];
    send(batch.map((p) => p.evaluation)).then(
      (decisions) => batch.forEach((p, i) => p.resolve(decisions[i] ?? false)),
      (error) => batch.forEach((p) => p.reject(error)),
    );
  }

  return function decide(evaluation: AuthzEvaluation): Promise<boolean> {
    return new Promise((resolve, reject) => {
      if (queue.length === 0) setTimeout(flush, 0);
      queue.push({ evaluation, resolve, reject });
    });
  };
}

export const decide = createAuthzBatcher();
