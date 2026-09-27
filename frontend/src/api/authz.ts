import { apiGet, apiPost } from './client';

/**
 * Backend `EVALUATION_RESOURCE_TYPES`: an unknown type fails the whole
 * request, so `authz.resourceTypes.test.ts` checks this list against it.
 */
export const AUTHZ_RESOURCE_TYPES = [
  'corpus_node',
  'edge',
  'task',
  'lead',
  'initiatief',
  'opdracht',
  'organisatie_eenheid',
  'tag',
  'samenwerkingsverband',
  'parlementair_item',
  'person',
  'initiatief_update',
  'lead_column',
  'lead_update',
  'lead_activity',
  'lead_attachment',
  'parlementair_abonnement',
  'mattermost_channel_link',
  'github_link',
  'stakeholder_assessment',
  'suggested_edge',
  'suggested_lead',
  // Only for the grant actions `role:assign` and `role:revoke`.
  'role',
] as const;

export type AuthzResourceType = (typeof AUTHZ_RESOURCE_TYPES)[number];

/** An existing resource (`id`), or one about to be created (optionally in `eenheidId`). */
export interface AuthzResource {
  type: AuthzResourceType;
  id?: string;
  eenheidId?: string;
  /** `org:create`: the type of the new eenheid. */
  eenheidType?: string;
  /**
   * Without `id`: is there any eenheid where the caller may create this?
   * With `role:assign` and no `roleId`: may the caller assign any role.
   */
  anywhere?: boolean;
  /** `person:place`: ending a placement (`placementId`: which one, so its bron counts), or placing a contact without account. */
  ending?: boolean;
  placementId?: string;
  contact?: boolean;
  /** Grant actions: the rol or role handed out, and to whom (neither: someone other than the caller). */
  rol?: string;
  roleId?: string;
  targetPersonId?: string;
  targetEenheidId?: string;
}

/** The `properties` of a resource on the wire, in the backend's names. */
export function authzProperties(resource: AuthzResource): Record<string, string | boolean> {
  const props: Record<string, string | boolean | undefined> = {
    eenheid_id: resource.eenheidId,
    eenheid_type: resource.eenheidType,
    anywhere: resource.anywhere || undefined,
    ending: resource.ending || undefined,
    placement_id: resource.placementId,
    contact: resource.contact || undefined,
    rol: resource.rol,
    role_id: resource.roleId,
    target_person_id: resource.targetPersonId,
    target_eenheid_id: resource.targetEenheidId,
  };
  return Object.fromEntries(
    Object.entries(props).filter((entry): entry is [string, string | boolean] => entry[1] !== undefined && entry[1] !== ''),
  );
}

interface AuthzEvaluation {
  /** A permission string such as `node:update`. */
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
type EvaluationOutcome = { ok: true; decision: boolean } | { ok: false; error: unknown };

/**
 * Ask the backend for decisions, in order, chunked to the request limit.
 * Chunks settle separately: one failed request fails only its own evaluations.
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

/** Collect every evaluation asked for in the same tick into one request. */
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

/** Answer of `GET /api/authz/eenheden`: `all` means every eenheid. */
export interface EenhedenWith {
  all: boolean;
  ids: string[];
}

/** The eenheden where the caller may do `action`, in one request. */
export function getEenhedenWith(action: string, eenheidType?: string): Promise<EenhedenWith> {
  return apiGet<EenhedenWith>('/api/authz/eenheden', {
    action,
    ...(eenheidType ? { eenheid_type: eenheidType } : {}),
  });
}
