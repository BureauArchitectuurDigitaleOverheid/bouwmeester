import { describe, it, expect } from 'vitest';
// The backend sources, read as text: the frontend has no other way to know
// which resource types the evaluation endpoint accepts.
import coreAuthz from '../../../backend/bouwmeester/core/authz.py?raw';
import schemaAuthz from '../../../backend/bouwmeester/schema/authz.py?raw';
import { AUTHZ_RESOURCE_TYPES } from './authz';

/** The string literals in a Python set or dict literal body. */
function quoted(body: string): string[] {
  return [...body.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
}

/** The top-level keys (four-space indent) of a dict literal starting at `opener`. */
function dictKeys(source: string, opener: string, closer: RegExp): string[] {
  const start = source.indexOf(opener);
  if (start < 0) throw new Error(`Not found in core/authz.py: ${opener}`);
  const rest = source.slice(start + opener.length);
  const end = rest.search(closer);
  if (end < 0) throw new Error(`No end of block after: ${opener}`);
  return [...rest.slice(0, end).matchAll(/^ {4}"([a-z_]+)":/gm)].map((m) => m[1]);
}

/**
 * `EVALUATION_RESOURCE_TYPES` as the backend builds it. The parse is strict
 * on purpose: when the backend changes how it builds the set, this fails
 * rather than silently comparing against a partial list.
 */
function backendResourceTypes(): string[] {
  const evaluation = schemaAuthz.match(/^EVALUATION_RESOURCE_TYPES = RESOURCE_TYPES \| \{([^}]*)\}$/m);
  expect(evaluation, 'EVALUATION_RESOURCE_TYPES changed shape').not.toBeNull();

  expect(coreAuthz).toMatch(/^RESOURCE_TYPES = frozenset\(set\(_LOCATORS\) \| _CREATE_ONLY_TYPES\)$/m);
  const createOnly = coreAuthz.match(/^_CREATE_ONLY_TYPES = frozenset\(\{([^}]*)\}\)$/m);
  expect(createOnly, '_CREATE_ONLY_TYPES changed shape').not.toBeNull();

  // `_LOCATORS` is a dict literal plus one loop adding the types without a
  // location; any other way of adding a key would go unseen here.
  const loop = 'for _type, _model in {\n';
  expect(coreAuthz.split(loop)).toHaveLength(2);
  expect(coreAuthz.match(/_LOCATORS\[[^\]]*\]\s*=/g)).toEqual(['_LOCATORS[_type] =']);
  expect(coreAuthz).not.toMatch(/_LOCATORS\.(update|setdefault)\(/);

  return [
    ...dictKeys(coreAuthz, '_LOCATORS: dict[str, _Locator] = {\n', /^\}$/m),
    ...dictKeys(coreAuthz, loop, /^\}\.items\(\):$/m),
    ...quoted(createOnly![1]),
    ...quoted(evaluation![1]),
  ];
}

describe('AUTHZ_RESOURCE_TYPES', () => {
  it('equals the backend EVALUATION_RESOURCE_TYPES', () => {
    const backend = backendResourceTypes();
    expect(new Set(backend).size).toBe(backend.length);
    expect([...AUTHZ_RESOURCE_TYPES].sort()).toEqual([...backend].sort());
  });
});
