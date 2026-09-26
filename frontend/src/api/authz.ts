import { apiPost } from './client';

/**
 * Resource types the evaluation endpoint accepts: mirrored by hand from
 * backend `schema/authz.py` `EVALUATION_RESOURCE_TYPES`, which is
 * `core/authz.py` `RESOURCE_TYPES` plus `role`.
 */
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
  | 'stakeholder_assessment'
  | 'suggested_edge'
  | 'suggested_lead'
  // Only for the grant action `role:assign`.
  | 'role';

/**
 * What an action is about: an existing resource (`id`), or one about to be
 * created, optionally in a given eenheid (`eenheidId`).
 */
export interface AuthzResource {
  type: AuthzResourceType;
  id?: string;
  eenheidId?: string;
  /** Without `id`: is there any eenheid where the caller may create this? */
  anywhere?: boolean;
  /** Grant actions: the rol (resource role) or role handed out ... */
  rol?: string;
  roleId?: string;
  /** ... and to whom; omitted means someone other than the caller. */
  targetPersonId?: string;
}

/** The `properties` of a resource on the wire, in the backend's names. */
export function authzProperties(resource: AuthzResource): Record<string, string | boolean> {
  const props: Record<string, string | boolean | undefined> = {
    eenheid_id: resource.eenheidId,
    anywhere: resource.anywhere || undefined,
    rol: resource.rol,
    role_id: resource.roleId,
    target_person_id: resource.targetPersonId,
  };
  return Object.fromEntries(
    Object.entries(props).filter((entry): entry is [string, string | boolean] => entry[1] !== undefined && entry[1] !== ''),
  );
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
  const properties = authzProperties(resource);
  return {
    action,
    resource: {
      type: resource.type,
      ...(resource.id ? { id: resource.id } : {}),
      ...(Object.keys(properties).length > 0 ? { properties } : {}),
    },
  };
}

/** One evaluation's answer, or why there is none (its chunk failed). */
export type EvaluationOutcome = { ok: true; decision: boolean } | { ok: false; error: unknown };

/**
 * Ask the backend for decisions, in order; chunked to the request limit.
 *
 * Chunks settle separately, so one failed request fails only its own
 * evaluations rather than every control asked about in the same tick.
 */
export async function evaluate(evaluations: AuthzEvaluation[]): Promise<EvaluationOutcome[]> {
  const chunks: AuthzEvaluation[][] = [];
  for (let i = 0; i < evaluations.length; i += MAX_EVALUATIONS) {
    chunks.push(evaluations.slice(i, i + MAX_EVALUATIONS));
  }
  const settled = await Promise.allSettled(
    chunks.map((chunk) =>
      apiPost<EvaluationsResponse>('/api/authz/evaluations', {
        evaluations: chunk.map(toWire),
      }),
    ),
  );
  return settled.flatMap((result, i): EvaluationOutcome[] =>
    result.status === 'fulfilled'
      ? chunks[i].map((_, j) => ({ ok: true, decision: result.value.evaluations[j]?.decision ?? false }))
      : chunks[i].map(() => ({ ok: false, error: result.reason })),
  );
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
      (outcomes) =>
        batch.forEach((p, i) => {
          const outcome = outcomes[i];
          if (!outcome) p.resolve(false);
          else if (outcome.ok) p.resolve(outcome.decision);
          else p.reject(outcome.error);
        }),
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
